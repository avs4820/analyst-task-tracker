from collections import Counter
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from openpyxl import load_workbook

from accounts.models import Department, User
from tracker.models import ProjectStream, Task, TaskStatus


EXPECTED_HEADERS = (
    "task_key",
    "project_stream",
    "department_code",
    "summary",
    "external_number",
    "external_url",
    "assignee_login",
    "task_status_code",
    "created_by_login",
)

REQUIRED_FIELDS = (
    "task_key",
    "project_stream",
    "department_code",
    "summary",
    "assignee_login",
    "task_status_code",
    "created_by_login",
)


class Command(BaseCommand):
    help = "Validate and import tasks from the agreed XLSX format."

    def add_arguments(self, parser):
        parser.add_argument("xlsx_path", type=Path)
        parser.add_argument(
            "--sheet",
            help=(
                "Worksheet name. By default uses 'Задачи', or the only "
                "worksheet when the workbook contains exactly one."
            ),
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
                "Replace active tasks in one transaction, deleting their related "
                "artifacts and weekly statuses. Archived tasks are preserved."
            ),
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Required together with --replace-existing outside dry-run.",
        )
        parser.add_argument(
            "--expected-existing-tasks",
            type=int,
            help=(
                "Abort replacement unless the current task count matches "
                "this value. Recommended for production runs."
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

        existing_count = Task.objects.count()
        expected_count = options["expected_existing_tasks"]
        if expected_count is not None and existing_count != expected_count:
            raise CommandError(
                "Existing task count changed: "
                f"expected {expected_count}, found {existing_count}."
            )

        rows, sheet_name = self._read_rows(path, options["sheet"])
        tasks, status_counts = self._validate_rows(rows)

        self.stdout.write(
            f"Validated {len(tasks)} tasks from worksheet '{sheet_name}'."
        )
        self.stdout.write(
            "Statuses: "
            + ", ".join(
                f"{code}={count}"
                for code, count in sorted(status_counts.items())
            )
        )
        if options["replace_existing"]:
            self.stdout.write(
                f"Existing tasks to replace: {existing_count}."
            )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing imported."))
            return

        with transaction.atomic():
            if options["replace_existing"]:
                Task.objects.all().delete()
            Task.objects.bulk_create(tasks)

        self.stdout.write(
            self.style.SUCCESS(f"Imported {len(tasks)} tasks successfully.")
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
            elif "Задачи" in workbook.sheetnames:
                worksheet = workbook["Задачи"]
            elif len(workbook.sheetnames) == 1:
                worksheet = workbook[workbook.sheetnames[0]]
            else:
                raise CommandError(
                    "Worksheet 'Задачи' not found in a multi-sheet workbook. "
                    "Use --sheet to select the task worksheet."
                )

            raw_rows = list(worksheet.iter_rows(values_only=True))
            if not raw_rows:
                raise CommandError("The selected worksheet is empty.")

            headers = tuple(self._clean_value(value) for value in raw_rows[0])
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
                if all(value is None or str(value).strip() == "" for value in values):
                    continue
                row = {
                    header: self._clean_value(value)
                    for header, value in zip(EXPECTED_HEADERS, values)
                }
                rows.append((excel_row, row))

            if not rows:
                raise CommandError("The selected worksheet has no task rows.")
            return rows, worksheet.title
        finally:
            workbook.close()

    def _validate_rows(self, rows):
        errors = []
        seen_keys = {}
        tasks = []
        status_counts = Counter()

        users = {
            user.login: user
            for user in User.objects.filter(is_active=True).select_related(
                "role", "department"
            )
        }
        departments = {
            department.code: department
            for department in Department.objects.filter(is_active=True)
        }
        statuses = {
            status.code: status
            for status in TaskStatus.objects.filter(is_active=True)
        }
        streams = {
            stream.name: stream
            for stream in ProjectStream.objects.filter(is_active=True)
        }

        for excel_row, row in rows:
            row_errors = []
            for field in REQUIRED_FIELDS:
                if not row[field]:
                    row_errors.append(f"{field} is required")

            task_key = row["task_key"]
            if task_key:
                if task_key in seen_keys:
                    row_errors.append(
                        f"duplicate task_key (first used in row {seen_keys[task_key]})"
                    )
                else:
                    seen_keys[task_key] = excel_row

            stream = streams.get(row["project_stream"])
            department = departments.get(row["department_code"])
            assignee = users.get(row["assignee_login"])
            status = statuses.get(row["task_status_code"])
            created_by = users.get(row["created_by_login"])

            references = (
                (stream, "project_stream", row["project_stream"]),
                (department, "department_code", row["department_code"]),
                (assignee, "assignee_login", row["assignee_login"]),
                (status, "task_status_code", row["task_status_code"]),
                (created_by, "created_by_login", row["created_by_login"]),
            )
            for obj, field, value in references:
                if value and obj is None:
                    row_errors.append(f"unknown or inactive {field}: {value!r}")

            if assignee:
                if assignee.role.code == "administrator":
                    row_errors.append("an administrator cannot be an assignee")
                elif (
                    assignee.role.code != "head"
                    and department
                    and assignee.department_id != department.id
                ):
                    row_errors.append(
                        "assignee department does not match department_code"
                    )

            if not row_errors and all(
                (stream, department, assignee, status, created_by)
            ):
                task = Task(
                    project_stream=stream,
                    department=department,
                    summary=row["summary"],
                    external_number=row["external_number"],
                    external_url=row["external_url"],
                    assignee=assignee,
                    status=status,
                    created_by=created_by,
                )
                try:
                    task.full_clean(validate_unique=False)
                except ValidationError as exc:
                    for field, messages in exc.message_dict.items():
                        row_errors.extend(
                            f"{field}: {message}" for message in messages
                        )
                if not row_errors:
                    tasks.append(task)
                    status_counts[status.code] += 1

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
        return tasks, status_counts

    @staticmethod
    def _clean_value(value):
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        return str(value).strip()
