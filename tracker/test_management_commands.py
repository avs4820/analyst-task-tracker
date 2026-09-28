import tempfile
from datetime import date
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from openpyxl import Workbook

from accounts.models import Department, Role, User
from tracker.management.commands.import_tasks import EXPECTED_HEADERS
from tracker.management.commands.import_weekly_statuses import (
    EXPECTED_HEADERS as WEEKLY_STATUS_HEADERS,
)
from tracker.models import (
    ProjectStream,
    Task,
    TaskArtifact,
    TaskStatus,
    TaskWeeklyStatus,
)


class TaskDataManagementCommandTests(TestCase):
    def setUp(self):
        self.department, _ = Department.objects.get_or_create(
            code="bsa",
            defaults={"name": "BSA", "is_active": True},
        )
        self.role, _ = Role.objects.get_or_create(
            code=Role.Code.EMPLOYEE,
            defaults={"name": "Employee"},
        )
        self.user = User.objects.create_user(
            login="analyst",
            name="Analyst",
            password="password",
            role=self.role,
            department=self.department,
        )
        self.stream = ProjectStream.objects.create(name="Stream")
        self.new_status = TaskStatus.objects.create(
            name="New",
            code="new",
            order=1,
        )
        self.done_status = TaskStatus.objects.create(
            name="Done",
            code="done",
            order=2,
            is_final=True,
        )
        self.temp_files = []

    def tearDown(self):
        for path in self.temp_files:
            path.unlink(missing_ok=True)

    def make_workbook(self, rows, sheet_name="Sheet1"):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = sheet_name
        worksheet.append(EXPECTED_HEADERS)
        for row in rows:
            worksheet.append([row.get(header, "") for header in EXPECTED_HEADERS])

        temporary = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        temporary.close()
        path = Path(temporary.name)
        workbook.save(path)
        workbook.close()
        self.temp_files.append(path)
        return path

    def make_weekly_status_workbook(self, rows, sheet_name="Sheet1"):
        workbook = Workbook()
        worksheet = workbook.active
        worksheet.title = sheet_name
        worksheet.append(WEEKLY_STATUS_HEADERS)
        for row in rows:
            worksheet.append(
                [row.get(header, "") for header in WEEKLY_STATUS_HEADERS]
            )

        temporary = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
        temporary.close()
        path = Path(temporary.name)
        workbook.save(path)
        workbook.close()
        self.temp_files.append(path)
        return path

    def valid_row(self, **overrides):
        row = {
            "task_key": "TASK-001",
            "project_stream": self.stream.name,
            "department_code": self.department.code,
            "summary": "Imported task",
            "external_number": "RND-1",
            "external_url": "https://tracker.example/RND-1",
            "assignee_login": self.user.login,
            "task_status_code": self.new_status.code,
            "created_by_login": self.user.login,
        }
        row.update(overrides)
        return row

    def create_existing_task(self):
        return Task.objects.create(
            project_stream=self.stream,
            department=self.department,
            summary="Existing task",
            assignee=self.user,
            status=self.new_status,
            created_by=self.user,
            external_number="RND-EXISTING",
        )

    def valid_weekly_status_row(self, **overrides):
        row = {
            "task_key": "RND-EXISTING",
            "week_start": "03.08.2026",
            "status_text": "Weekly progress",
            "updated_by_login": self.user.login,
        }
        row.update(overrides)
        return row

    def test_import_tasks_dry_run_validates_without_writing(self):
        path = self.make_workbook([self.valid_row()])

        call_command("import_tasks", path, dry_run=True)

        self.assertEqual(Task.objects.count(), 0)

    def test_import_tasks_creates_tasks_from_single_sheet_workbook(self):
        path = self.make_workbook(
            [
                self.valid_row(),
                self.valid_row(
                    task_key="TASK-002",
                    summary="Second imported task",
                    external_number="",
                    external_url="",
                    task_status_code="done",
                ),
            ]
        )

        call_command("import_tasks", path)

        self.assertEqual(Task.objects.count(), 2)
        imported = Task.objects.get(external_number="RND-1")
        self.assertEqual(imported.assignee, self.user)
        self.assertEqual(imported.department, self.department)
        self.assertEqual(imported.created_by, self.user)

    def test_import_tasks_rejects_duplicate_task_keys(self):
        path = self.make_workbook(
            [
                self.valid_row(),
                self.valid_row(summary="Duplicate task"),
            ]
        )

        with self.assertRaisesMessage(CommandError, "duplicate task_key"):
            call_command("import_tasks", path, dry_run=True)

        self.assertEqual(Task.objects.count(), 0)

    def test_invalid_replacement_preserves_existing_tasks(self):
        existing = self.create_existing_task()
        path = self.make_workbook(
            [self.valid_row(assignee_login="missing-user")]
        )

        with self.assertRaisesMessage(CommandError, "missing-user"):
            call_command(
                "import_tasks",
                path,
                replace_existing=True,
                confirm=True,
                expected_existing_tasks=1,
            )

        self.assertTrue(Task.objects.filter(pk=existing.pk).exists())

    def test_atomic_replacement_deletes_related_data_and_imports_tasks(self):
        existing = self.create_existing_task()
        TaskArtifact.objects.create(
            task=existing,
            name="Artifact",
            url="https://example.com/artifact",
            created_by=self.user,
        )
        TaskWeeklyStatus.objects.create(
            task=existing,
            week_start=date(2026, 8, 3),
            text="Old weekly status",
            updated_by=self.user,
        )
        path = self.make_workbook([self.valid_row()])

        call_command(
            "import_tasks",
            path,
            replace_existing=True,
            confirm=True,
            expected_existing_tasks=1,
        )

        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(Task.objects.get().summary, "Imported task")
        self.assertEqual(TaskArtifact.objects.count(), 0)
        self.assertEqual(TaskWeeklyStatus.objects.count(), 0)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(Department.objects.filter(pk=self.department.pk).exists())
        self.assertTrue(TaskStatus.objects.filter(pk=self.new_status.pk).exists())
        self.assertTrue(ProjectStream.objects.filter(pk=self.stream.pk).exists())

    def test_clear_tracker_data_dry_run_does_not_delete(self):
        task = self.create_existing_task()

        call_command("clear_tracker_data", dry_run=True, expected_tasks=1)

        self.assertTrue(Task.objects.filter(pk=task.pk).exists())

    def create_archived_task_with_history(self):
        task = self.create_existing_task()
        artifact = TaskArtifact.objects.create(
            task=task, name="Archived artifact", url="https://example.com/archived",
            created_by=self.user,
        )
        weekly = TaskWeeklyStatus.objects.create(
            task=task, week_start=date(2026, 8, 3), text="Archived history",
            updated_by=self.user,
        )
        Task.objects.filter(pk=task.pk).archive(self.user)
        return task, artifact, weekly

    def assert_archive_preserved(self, task, artifact, weekly):
        task.refresh_from_db()
        self.assertTrue(task.is_archived)
        self.assertTrue(TaskArtifact.objects.filter(pk=artifact.pk, task=task).exists())
        self.assertTrue(TaskWeeklyStatus.objects.filter(pk=weekly.pk, task=task, text="Archived history").exists())

    def test_clear_preserves_archived_tasks_and_history(self):
        archived = self.create_archived_task_with_history()
        active = self.create_existing_task()
        call_command("clear_tracker_data", confirm=True, expected_tasks=1)
        self.assertFalse(Task.all_objects.filter(pk=active.pk).exists())
        self.assert_archive_preserved(*archived)

    def test_task_replacement_preserves_archive_even_with_same_external_number(self):
        archived = self.create_archived_task_with_history()
        active = self.create_existing_task()
        path = self.make_workbook([self.valid_row(external_number=archived[0].external_number)])
        call_command("import_tasks", path, replace_existing=True, confirm=True, expected_existing_tasks=1)
        self.assertFalse(Task.all_objects.filter(pk=active.pk).exists())
        self.assertEqual(Task.objects.count(), 1)
        self.assert_archive_preserved(*archived)

    def test_weekly_import_rejects_archived_task(self):
        archived = self.create_archived_task_with_history()
        path = self.make_weekly_status_workbook([self.valid_weekly_status_row()])
        with self.assertRaises(CommandError):
            call_command("import_weekly_statuses", path)
        self.assert_archive_preserved(*archived)

    def test_weekly_replacement_only_changes_active_history(self):
        archived = self.create_archived_task_with_history()
        active = self.create_existing_task()
        TaskWeeklyStatus.objects.create(
            task=active, week_start=date(2026, 8, 3), text="Replace this",
            updated_by=self.user,
        )
        path = self.make_weekly_status_workbook([self.valid_weekly_status_row()])
        call_command("import_weekly_statuses", path, replace_existing=True,
                     confirm=True, expected_existing_statuses=1)
        self.assertEqual(active.weekly_statuses.get().text, "Weekly progress")
        self.assert_archive_preserved(*archived)

    def test_weekly_import_ignores_archive_when_matching_active_task(self):
        archived = self.create_archived_task_with_history()
        active = self.create_existing_task()
        path = self.make_weekly_status_workbook([self.valid_weekly_status_row()])
        call_command("import_weekly_statuses", path)
        self.assertEqual(active.weekly_statuses.get().text, "Weekly progress")
        self.assert_archive_preserved(*archived)

    def test_clear_tracker_data_deletes_only_task_owned_data(self):
        task = self.create_existing_task()
        TaskArtifact.objects.create(
            task=task,
            name="Artifact",
            url="https://example.com/artifact",
            created_by=self.user,
        )
        TaskWeeklyStatus.objects.create(
            task=task,
            week_start=date(2026, 8, 3),
            text="Weekly status",
            updated_by=self.user,
        )

        call_command("clear_tracker_data", confirm=True, expected_tasks=1)

        self.assertEqual(Task.objects.count(), 0)
        self.assertEqual(TaskArtifact.objects.count(), 0)
        self.assertEqual(TaskWeeklyStatus.objects.count(), 0)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(Department.objects.filter(pk=self.department.pk).exists())
        self.assertTrue(TaskStatus.objects.filter(pk=self.new_status.pk).exists())
        self.assertTrue(ProjectStream.objects.filter(pk=self.stream.pk).exists())

    def test_import_weekly_statuses_dry_run_does_not_write(self):
        self.create_existing_task()
        path = self.make_weekly_status_workbook(
            [self.valid_weekly_status_row()]
        )

        call_command(
            "import_weekly_statuses",
            path,
            dry_run=True,
            expected_existing_statuses=0,
        )

        self.assertEqual(TaskWeeklyStatus.objects.count(), 0)

    def test_import_weekly_statuses_creates_history(self):
        task = self.create_existing_task()
        path = self.make_weekly_status_workbook(
            [
                self.valid_weekly_status_row(week_start="27.07.2026"),
                self.valid_weekly_status_row(
                    week_start=date(2026, 8, 3),
                    status_text="Current progress",
                ),
            ]
        )

        call_command("import_weekly_statuses", path)

        statuses = TaskWeeklyStatus.objects.filter(task=task).order_by(
            "week_start"
        )
        self.assertEqual(statuses.count(), 2)
        self.assertEqual(statuses[0].week_start, date(2026, 7, 27))
        self.assertEqual(statuses[1].updated_by, self.user)
        self.assertEqual(statuses[1].text, "Current progress")

    def test_import_weekly_statuses_rejects_duplicate_task_week(self):
        self.create_existing_task()
        path = self.make_weekly_status_workbook(
            [
                self.valid_weekly_status_row(),
                self.valid_weekly_status_row(status_text="Duplicate"),
            ]
        )

        with self.assertRaisesMessage(
            CommandError,
            "duplicate task_key and week_start",
        ):
            call_command("import_weekly_statuses", path, dry_run=True)

        self.assertEqual(TaskWeeklyStatus.objects.count(), 0)

    def test_import_weekly_statuses_rejects_invalid_references_and_week(self):
        self.create_existing_task()
        path = self.make_weekly_status_workbook(
            [
                self.valid_weekly_status_row(
                    task_key="RND-MISSING",
                    week_start="02.08.2026",
                    updated_by_login="missing-user",
                )
            ]
        )

        with self.assertRaises(CommandError) as context:
            call_command("import_weekly_statuses", path, dry_run=True)

        error = str(context.exception)
        self.assertIn("week_start must be a Monday", error)
        self.assertIn("unknown task_key", error)
        self.assertIn("unknown or inactive updated_by_login", error)

    def test_import_weekly_statuses_replaces_only_weekly_history(self):
        task = self.create_existing_task()
        TaskWeeklyStatus.objects.create(
            task=task,
            week_start=date(2026, 7, 27),
            text="Old history",
            updated_by=self.user,
        )
        path = self.make_weekly_status_workbook(
            [self.valid_weekly_status_row(status_text="Replacement history")]
        )

        call_command(
            "import_weekly_statuses",
            path,
            replace_existing=True,
            confirm=True,
            expected_existing_statuses=1,
        )

        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(TaskWeeklyStatus.objects.count(), 1)
        imported = TaskWeeklyStatus.objects.get()
        self.assertEqual(imported.task, task)
        self.assertEqual(imported.text, "Replacement history")

    def test_invalid_weekly_replacement_preserves_existing_history(self):
        task = self.create_existing_task()
        existing = TaskWeeklyStatus.objects.create(
            task=task,
            week_start=date(2026, 7, 27),
            text="Existing history",
            updated_by=self.user,
        )
        path = self.make_weekly_status_workbook(
            [self.valid_weekly_status_row(updated_by_login="missing-user")]
        )

        with self.assertRaisesMessage(CommandError, "missing-user"):
            call_command(
                "import_weekly_statuses",
                path,
                replace_existing=True,
                confirm=True,
                expected_existing_statuses=1,
            )

        self.assertTrue(
            TaskWeeklyStatus.objects.filter(pk=existing.pk).exists()
        )
