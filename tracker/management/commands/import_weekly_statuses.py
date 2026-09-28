from collections import Counter
from datetime import date, datetime
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from accounts.models import User
from tracker.models import Task, TaskWeeklyStatus
from tracker.utils import get_week_start


EXPECTED_HEADERS = (
    "task_key",
    "week_start",
    "status_text",
    "updated_by_login",
)


class Command(BaseCommand):
    help = "Validate and import task weekly statuses from the agreed XLSX format."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=Path)
        parser.add_argument(
            "--sheet",
            help="Worksheet name. By default uses the only worksheet.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate the complete file without changing the database.",
        )
        parser.add_argument(
            "--replace-existing",
            action="store_true",
            help=(
                "Replace weekly statuses of active tasks in one transaction. "
                "Archived tasks and their history are preserved."
            ),
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required together with --replace-existing outside dry-run.",
        )
        parser.add_argument(
            "--expected-existing-statuses",
            type=int,
            help=(
                "Abort unless the current weekly status count matches this value. "
                "Recommended for production runs."
            ),
        )

    def handle(self, *args, **options):
        path = options["xlsx_path"].resolve()
        if not path.is_file():
            raise CommandError(f"XLSX file not found: {path}")
        if path.suffix.lower() != ".xlsx":
            raise CommandError("The import file must have the .xlsx extension.")
        if options["replace_existing"] and not (
            options["dry_run"] or options["confirm"]
        ):
            raise CommandError(
                "--replace-existing requires --confirm, or use --dry-run."
            )
        if options["confirm"] and not options["replace_existing"]:
            raise CommandError("--confirm is only valid with --replace-existing.")

        existing_count = TaskWeeklyStatus.objects.filter(task__archived_at__isnull=True).count()
        expected_count = options["expected_existing_statuses"]
        if expected_count is not None and existing_count != expected_count:
            raise CommandError(
                "Existing weekly status count changed: "
                f"expected {expected_count}, found {existing_count}."
            )

        rows, sheet_name = self._read_rows(path, options["sheet"])
        statuses, counts = self._validate_rows(
            rows,
            replace_existing=options["replace_existing"],
        )

        self.stdout.write(
            f"Validated {len(statuses)} weekly statuses from worksheet "
            f"'{sheet_name}'."
        )
        self.stdout.write(
            f"Tasks represented: {len(counts['tasks'])}; "
            f"weeks: {len(counts['weeks'])}; "
            f"updaters: {len(counts['users'])}."
        )
        self.stdout.write(
            f"Week range: {min(counts['weeks'])} to {max(counts['weeks'])}."
        )
        if options["replace_existing"]:
            self.stdout.write(
                f"Existing weekly statuses to replace: {existing_count}."
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing imported."))
            return

        with transaction.atomic():
            if options["replace_existing"]:
                TaskWeeklyStatus.objects.filter(task__archived_at__isnull=True).delete()
            TaskWeeklyStatus.objects.bulk_create(statuses)

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported {len(statuses)} weekly statuses successfully."
            )
        )

    def _read_rows(self, path, requested_sheet):
        try:
            workbook = load_workbook(
                filename=path,
                read_only=True,
                data_only=False,
            )
        except Exception as exc:
            raise CommandError(f"Cannot read XLSX file: {exc}") from exc

        try:
            if requested_sheet:
                if requested_sheet not in workbook.sheetnames:
                    raise CommandError(
                        f"Worksheet '{requested_sheet}' not found. "
                        f"Available: {', '.join(workbook.sheetnames)}."
                    )
                worksheet = workbook[requested_sheet]
            elif len(workbook.sheetnames) == 1:
                worksheet = workbook[workbook.sheetnames[0]]
            else:
                raise CommandError(
                    "The workbook contains multiple worksheets. "
                    "Use --sheet to select one."
                )

            raw_rows = list(worksheet.iter_rows(values_only=True))
            if not raw_rows:
                raise CommandError("The selected worksheet is empty.")

            headers = tuple(self._clean_text(value) for value in raw_rows[0])
            while headers and headers[-1] == "":
                headers = headers[:-1]
            if headers != EXPECTED_HEADERS:
                raise CommandError(
                    "Unexpected headers. Expected exactly: "
                    + ", ".join(EXPECTED_HEADERS)
                )

            rows = []
            for excel_row, values in enumerate(raw_rows[1:], start=2):
                values = values[: len(EXPECTED_HEADERS)]
                if all(
                    value is None or str(value).strip() == "" for value in values
                ):
                    continue
                rows.append(
                    (
                        excel_row,
                        {
                            header: value
                            for header, value in zip(EXPECTED_HEADERS, values)
                        },
                    )
                )

            if not rows:
                raise CommandError(
                    "The selected worksheet has no weekly status rows."
                )
            return rows, worksheet.title
        finally:
            workbook.close()

    def _validate_rows(self, rows, *, replace_existing):
        errors = []
        seen_pairs = {}
        statuses_to_create = []
        task_counts = Counter()
        week_counts = Counter()
        user_counts = Counter()

        tasks_by_external_number = {}
        duplicate_external_numbers = set()
        for task in Task.objects.exclude(external_number=""):
            if task.external_number in tasks_by_external_number:
                duplicate_external_numbers.add(task.external_number)
            else:
                tasks_by_external_number[task.external_number] = task

        users = {
            user.login: user for user in User.objects.filter(is_active=True)
        }
        existing_pairs = set()
        if not replace_existing:
            existing_pairs = set(
                TaskWeeklyStatus.objects.filter(task__archived_at__isnull=True).values_list(
                    "task__external_number",
                    "week_start",
                )
            )

        current_week_start = get_week_start(timezone.localdate())

        for excel_row, raw_row in rows:
            task_key = self._clean_text(raw_row["task_key"])
            status_text = self._clean_text(raw_row["status_text"])
            updated_by_login = self._clean_text(raw_row["updated_by_login"])
            week_start = self._parse_date(raw_row["week_start"])
            row_errors = []

            if not task_key:
                row_errors.append("task_key is required")
            if week_start is None:
                row_errors.append(
                    f"invalid week_start: {raw_row['week_start']!r}"
                )
            elif week_start.weekday() != 0:
                row_errors.append("week_start must be a Monday")
            elif week_start > current_week_start:
                row_errors.append("week_start cannot be in a future week")
            if not status_text:
                row_errors.append("status_text is required")
            if not updated_by_login:
                row_errors.append("updated_by_login is required")

            task = tasks_by_external_number.get(task_key)
            if task_key in duplicate_external_numbers:
                row_errors.append(
                    f"ambiguous task_key; multiple tasks use external_number {task_key!r}"
                )
                task = None
            elif task_key and task is None:
                row_errors.append(f"unknown task_key: {task_key!r}")

            updated_by = users.get(updated_by_login)
            if updated_by_login and updated_by is None:
                row_errors.append(
                    "unknown or inactive updated_by_login: "
                    f"{updated_by_login!r}"
                )

            pair = (task_key, week_start)
            if task_key and week_start:
                if pair in seen_pairs:
                    row_errors.append(
                        "duplicate task_key and week_start "
                        f"(first used in row {seen_pairs[pair]})"
                    )
                else:
                    seen_pairs[pair] = excel_row
                if pair in existing_pairs:
                    row_errors.append(
                        "weekly status already exists; use --replace-existing "
                        "to replace the complete history"
                    )

            if not row_errors and task and updated_by and week_start:
                weekly_status = TaskWeeklyStatus(
                    task=task,
                    week_start=week_start,
                    text=status_text,
                    updated_by=updated_by,
                )
                try:
                    weekly_status.full_clean(
                        exclude=("task", "updated_by"),
                        validate_unique=False,
                        validate_constraints=False,
                    )
                except ValidationError as exc:
                    for field, messages in exc.message_dict.items():
                        row_errors.extend(
                            f"{field}: {message}" for message in messages
                        )
                if not row_errors:
                    statuses_to_create.append(weekly_status)
                    task_counts[task_key] += 1
                    week_counts[week_start] += 1
                    user_counts[updated_by_login] += 1

            if row_errors:
                errors.append(
                    f"Row {excel_row} ({task_key or 'no task_key'}): "
                    + "; ".join(row_errors)
                )

        if errors:
            raise CommandError(
                f"Import validation failed with {len(errors)} invalid rows:\n"
                + "\n".join(errors)
            )

        return statuses_to_create, {
            "tasks": task_counts,
            "weeks": week_counts,
            "users": user_counts,
        }

    @staticmethod
    def _parse_date(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        text = Command._clean_text(value)
        for date_format in ("%d.%m.%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, date_format).date()
            except ValueError:
                continue
        return None

    @staticmethod
    def _clean_text(value):
        if value is None:
            return ""
        return str(value).strip()
