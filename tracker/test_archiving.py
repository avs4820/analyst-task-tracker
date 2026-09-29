from datetime import timedelta
from io import BytesIO
from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from accounts.models import Department, Role, User
from tracker.models import ProjectStream, Task, TaskArtifact, TaskStatus, TaskWeeklyStatus
from tracker.utils import get_week_start


class TaskArchivingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department, _ = Department.objects.get_or_create(code="bsa", defaults={"name": "BSA"})
        cls.users = []
        for code in ("employee", "manager", "head", "administrator"):
            role, _ = Role.objects.get_or_create(code=code, defaults={"name": code})
            cls.users.append(User.objects.create(
                login=f"archive_{code}", name=code, role=role, department=cls.department,
            ))
        cls.superuser = User.objects.create(
            login="archive_superuser", name="Superuser", role=cls.users[-1].role,
            department=cls.department, is_superuser=True, is_staff=True,
        )
        cls.stream = ProjectStream.objects.create(name="Archive stream")
        cls.status = TaskStatus.objects.create(name="Archive test status", code="archive-test")
        cls.task = Task.objects.create(
            summary="Private archived task", external_number="ARC-1",
            department=cls.department, project_stream=cls.stream,
            assignee=cls.users[0], created_by=cls.superuser, status=cls.status,
        )
        cls.active = Task.objects.create(
            summary="Visible active task", department=cls.department,
            project_stream=cls.stream, assignee=cls.users[0],
            created_by=cls.superuser, status=cls.status,
        )
        cls.artifact = TaskArtifact.objects.create(
            task=cls.task, name="Private archive artifact", url="https://example.com/archive",
            created_by=cls.superuser,
        )
        cls.weekly = TaskWeeklyStatus.objects.create(
            task=cls.task, week_start=get_week_start(timezone.localdate()) - timedelta(weeks=1),
            text="Private archive history", updated_by=cls.users[0],
        )
        cls.changelist = reverse("admin:tracker_task_changelist")

    def archive(self):
        Task.objects.filter(pk=self.task.pk).archive(self.superuser)

    def action(self, action="archive_tasks", ids=None, confirm=True, query="", across=False):
        data = {
            "action": action, "_selected_action": ids or [self.task.pk],
            "select_across": "1" if across else "0",
        }
        if confirm:
            data["confirm_archive"] = "yes"
        return self.client.post(self.changelist + query, data)

    def test_archive_restore_preserve_content_relations_and_timestamps(self):
        before = Task.all_objects.values().get(pk=self.task.pk)
        artifact_before = TaskArtifact.objects.values().get(pk=self.artifact.pk)
        weekly_before = TaskWeeklyStatus.objects.values().get(pk=self.weekly.pk)
        self.archive()
        self.task.refresh_from_db()
        archived_at = self.task.archived_at
        self.assertEqual(self.task.archived_by, self.superuser)
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())
        self.assertFalse(self.users[0].assigned_tasks.filter(pk=self.task.pk).exists())
        self.assertEqual(Task.all_objects.filter(pk=self.task.pk).archive(self.users[0]), 0)
        self.task.refresh_from_db()
        self.assertEqual(self.task.archived_at, archived_at)
        self.assertEqual(self.task.archived_by, self.superuser)
        self.assertEqual(Task.all_objects.filter(pk=self.task.pk).restore(), 1)
        self.assertEqual(Task.all_objects.filter(pk=self.task.pk).restore(), 0)
        self.assertEqual(Task.objects.values().get(pk=self.task.pk), before)
        self.assertEqual(TaskArtifact.objects.values().get(pk=self.artifact.pk), artifact_before)
        self.assertEqual(TaskWeeklyStatus.objects.values().get(pk=self.weekly.pk), weekly_before)

    def test_archive_is_absent_from_pages_search_counters_and_excel_for_every_role(self):
        self.archive()
        for user in [*self.users, self.superuser]:
            self.client.force_login(user)
            with self.subTest(role=user.login):
                for name in ("task-list", "status-summary", "dashboard"):
                    response = self.client.get(reverse(f"tracker:{name}"), {"show_done": "1", "show_cancelled": "1", "show_final": "1", "only_mine": "0"})
                    self.assertEqual(response.status_code, 200)
                    self.assertNotContains(response, self.task.summary)
                    self.assertNotContains(response, self.artifact.name)
                    self.assertNotContains(response, self.weekly.text)
                listing = self.client.get(reverse("tracker:task-list"), {"only_mine": "0"})
                self.assertEqual(listing.context["page_obj"].paginator.count, 1)
                search = self.client.get(reverse("tracker:task-list"), {"search": "ARC-1", "only_mine": "0"})
                self.assertEqual(search.context["page_obj"].paginator.count, 0)
                response = self.client.get(reverse("tracker:status-summary"), {"format": "xlsx", "show_final": "1"})
                self.assertEqual(response.status_code, 200)
                workbook = load_workbook(BytesIO(response.content))
                values = str(list(workbook.active.values))
                workbook.close()
                self.assertNotIn(self.task.summary, values)
                self.assertNotIn(self.weekly.text, values)
                self.assertIn(self.active.summary, values)

    def test_archived_read_and_write_endpoints_return_404_for_every_role(self):
        self.archive()
        for user in [*self.users, self.superuser]:
            self.client.force_login(user)
            with self.subTest(role=user.login):
                edit = reverse("tracker:task-update", args=[self.task.pk])
                self.assertEqual(self.client.get(edit).status_code, 404)
                self.assertEqual(self.client.post(edit, {}).status_code, 404)
                for name in ("task-inline-update", "task-status-update", "task-artifact-create"):
                    self.assertEqual(self.client.post(reverse(f"tracker:{name}", args=[self.task.pk]), {}).status_code, 404)
                self.assertEqual(self.client.post(reverse("tracker:task-artifact-delete", args=[self.task.pk, self.artifact.pk])).status_code, 404)
                self.assertEqual(self.client.post(reverse("tracker:task-list"), {"task_id": self.task.pk, "text": "changed"}).status_code, 404)
        self.weekly.refresh_from_db()
        self.assertEqual(self.weekly.text, "Private archive history")
        self.assertTrue(TaskArtifact.objects.filter(pk=self.artifact.pk).exists())

    def test_restored_task_uses_current_permissions(self):
        self.archive()
        Task.all_objects.filter(pk=self.task.pk).restore()
        self.client.force_login(self.users[0])
        url = reverse("tracker:task-update", args=[self.task.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        Task.objects.filter(pk=self.task.pk).update(assignee=self.users[1])
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_admin_confirmation_bulk_archive_filter_and_restore(self):
        self.client.force_login(self.superuser)
        response = self.action(ids=[self.task.pk, self.active.pk], confirm=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["count"], 2)
        self.assertEqual(Task.objects.count(), 2)
        self.assertEqual(self.action(ids=[self.task.pk, self.active.pk]).status_code, 302)
        self.assertEqual(Task.objects.count(), 0)
        listing = self.client.get(self.changelist)
        self.assertEqual(listing.context["cl"].result_count, 0)
        archived = self.client.get(self.changelist, {"archive": "archived"})
        self.assertEqual(archived.context["cl"].result_count, 2)
        response = self.action("restore_tasks", query="?archive=archived", ids=[self.task.pk, self.active.pk], confirm=False)
        self.assertEqual(response.context["count"], 2)
        self.assertEqual(self.action("restore_tasks", query="?archive=archived", ids=[self.task.pk, self.active.pk]).status_code, 302)
        self.assertEqual(Task.objects.count(), 2)
        self.assertEqual(LogEntry.objects.filter(user=self.superuser).count(), 4)

    def test_select_across_archives_entire_filtered_selection(self):
        self.client.force_login(self.superuser)
        Task.objects.bulk_create([
            Task(summary=f"Bulk target {index}", department=self.department,
                 project_stream=self.stream, assignee=self.users[0], created_by=self.superuser, status=self.status)
            for index in range(101)
        ])
        first = Task.objects.filter(summary__startswith="Bulk target").first()
        response = self.action(ids=[first.pk], query="?q=Bulk+target", across=True, confirm=False)
        self.assertEqual(response.context["count"], 101)
        self.assertEqual(response.context["select_across"], "1")
        self.action(ids=[first.pk], query="?q=Bulk+target", across=True)
        self.assertEqual(Task.all_objects.filter(archived_at__isnull=False).count(), 101)
        self.assertEqual(Task.objects.count(), 2)

    def test_admin_transaction_rolls_back_if_logging_fails(self):
        self.client.force_login(self.superuser)
        with patch("tracker.admin.TaskAdmin.log_change", side_effect=RuntimeError("log failed")):
            with self.assertRaises(RuntimeError):
                self.action(ids=[self.task.pk, self.active.pk])
        self.assertEqual(Task.objects.count(), 2)
        self.assertEqual(LogEntry.objects.count(), 0)

    def test_archive_is_read_only_in_admin_including_artifacts(self):
        self.archive()
        self.client.force_login(self.superuser)
        task_url = reverse("admin:tracker_task_change", args=[self.task.pk])
        response = self.client.get(task_url)
        self.assertContains(response, self.task.summary)
        self.assertContains(response, self.artifact.name)
        self.assertContains(response, self.weekly.text)
        self.assertFalse(response.context["has_change_permission"])
        self.assertEqual(self.client.post(task_url, {"summary": "changed"}).status_code, 403)
        artifact_url = reverse("admin:tracker_taskartifact_change", args=[self.artifact.pk])
        self.assertEqual(self.client.get(artifact_url).status_code, 200)
        self.assertEqual(self.client.post(artifact_url, {"name": "changed"}).status_code, 403)
        for model, pk in (("task", self.task.pk), ("taskartifact", self.artifact.pk)):
            self.assertEqual(self.client.post(reverse(f"admin:tracker_{model}_delete", args=[pk]), {"post": "yes"}).status_code, 403)
            response = self.client.post(reverse(f"admin:tracker_{model}_changelist") + "?archive=all" if model == "task" else reverse(f"admin:tracker_{model}_changelist"), {
                "action": "delete_selected", "_selected_action": [pk], "post": "yes",
            })
            self.assertEqual(response.status_code, 403)
        self.assertTrue(Task.all_objects.filter(pk=self.task.pk).exists())
        self.assertTrue(TaskArtifact.objects.filter(pk=self.artifact.pk).exists())

    def test_only_superuser_can_archive_or_access_archive_in_admin(self):
        staff = self.users[-1]
        staff.is_staff = True
        staff.save()
        staff.user_permissions.set(Permission.objects.filter(content_type__app_label="tracker"))
        self.client.force_login(staff)
        response = self.client.get(self.changelist)
        self.assertNotContains(response, 'value="archive_tasks"')
        self.assertNotContains(response, 'value="restore_tasks"')
        self.action()
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())
        self.archive()
        self.assertNotContains(self.client.get(self.changelist, {"archive": "all"}), self.task.summary)
        response = self.client.get(reverse("admin:tracker_task_change", args=[self.task.pk]), follow=True)
        self.assertNotContains(response, self.artifact.name)
        self.assertNotContains(self.client.get(reverse("admin:tracker_taskartifact_changelist")), self.artifact.name)
        self.action("restore_tasks", query="?archive=all")
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())

    def test_autocomplete_cannot_select_archived_tasks(self):
        self.archive()
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("admin:autocomplete"), {
            "app_label": "tracker", "model_name": "taskartifact", "field_name": "task", "term": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()["results"]], [str(self.active.pk)])
