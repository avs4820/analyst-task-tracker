from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse
from tracker.utils import get_week_start

from accounts.models import Department, Role, User
from tracker.decorators import role_required
from tracker.forms import (
    TaskForm,
    TaskInlineEditForm,
    TaskPopupCreateForm,
    get_assignable_users,
)
from tracker.models import (
    ProjectStream,
    Task,
    TaskArtifact,
    TaskStatus,
    TaskWeeklyStatus,
)


def get_bsa_department():
    department, _ = Department.objects.get_or_create(
        code="bsa",
        defaults={
            "name": "BSA",
            "is_active": True,
        },
    )
    return department


class TaskAssigneeQuerysetTests(TestCase):
    def setUp(self):
        self.bsa_department = get_bsa_department()
        self.support_department = Department.objects.create(
            code="support",
            name="Support",
            is_active=True,
        )

        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )
        self.manager_role, _ = Role.objects.get_or_create(
            code="manager",
            defaults={"name": "Manager"},
        )
        self.head_role, _ = Role.objects.get_or_create(
            code="head",
            defaults={"name": "Head"},
        )
        self.administrator_role, _ = Role.objects.get_or_create(
            code="administrator",
            defaults={"name": "Administrator"},
        )

        self.bsa_employee = User.objects.create(
            login="assignee_bsa_employee",
            name="BSA Employee",
            role=self.employee_role,
            department=self.bsa_department,
        )
        self.second_bsa_employee = User.objects.create(
            login="assignee_second_bsa_employee",
            name="Second BSA Employee",
            role=self.employee_role,
            department=self.bsa_department,
        )
        self.support_employee = User.objects.create(
            login="assignee_support_employee",
            name="Support Employee",
            role=self.employee_role,
            department=self.support_department,
        )

        self.bsa_manager = User.objects.create(
            login="assignee_bsa_manager",
            name="BSA Manager",
            role=self.manager_role,
            department=self.bsa_department,
        )
        self.second_bsa_manager = User.objects.create(
            login="assignee_second_bsa_manager",
            name="Second BSA Manager",
            role=self.manager_role,
            department=self.bsa_department,
        )
        self.support_manager = User.objects.create(
            login="assignee_support_manager",
            name="Support Manager",
            role=self.manager_role,
            department=self.support_department,
        )

        self.head = User.objects.create(
            login="assignee_head",
            name="Head",
            role=self.head_role,
            department=self.bsa_department,
        )
        self.second_head = User.objects.create(
            login="assignee_second_head",
            name="Second Head",
            role=self.head_role,
            department=self.support_department,
        )

        self.administrator = User.objects.create(
            login="assignee_administrator",
            name="Administrator",
            role=self.administrator_role,
            department=self.bsa_department,
        )
        self.second_administrator = User.objects.create(
            login="assignee_second_administrator",
            name="Second Administrator",
            role=self.administrator_role,
            department=self.support_department,
        )

        self.inactive_employee = User.objects.create(
            login="assignee_inactive_employee",
            name="Inactive Employee",
            role=self.employee_role,
            department=self.bsa_department,
            is_active=False,
        )

        self.project_stream = ProjectStream.objects.create(
            name="Проверка исполнителей",
        )
        self.status = TaskStatus.objects.create(
            name="Новая",
            code="new",
            order=1,
            is_active=True,
        )

        self.task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.bsa_department,
            summary="Задача отдела BSA",
            assignee=self.bsa_employee,
            status=self.status,
            created_by=self.bsa_manager,
        )

    def test_employee_can_assign_only_self(self):
        users = set(
            get_assignable_users(
                user=self.bsa_employee,
            )
        )

        self.assertEqual(
            users,
            {self.bsa_employee},
        )

    def test_manager_can_assign_self_and_employees_of_own_department(self):
        users = set(
            get_assignable_users(
                user=self.bsa_manager,
            )
        )

        self.assertEqual(
            users,
            {
                self.bsa_manager,
                self.bsa_employee,
                self.second_bsa_employee,
            },
        )

    def test_manager_cannot_assign_users_from_another_department(self):
        users = get_assignable_users(
            user=self.bsa_manager,
        )

        self.assertNotIn(self.support_employee, users)
        self.assertNotIn(self.support_manager, users)

    def test_manager_cannot_assign_other_manager_head_or_administrator(self):
        users = get_assignable_users(
            user=self.bsa_manager,
        )

        self.assertNotIn(self.second_bsa_manager, users)
        self.assertNotIn(self.head, users)
        self.assertNotIn(self.administrator, users)

    def test_head_can_assign_self_managers_and_employees_from_all_departments(self):
        users = set(
            get_assignable_users(
                user=self.head,
            )
        )

        self.assertEqual(
            users,
            {
                self.head,
                self.bsa_employee,
                self.second_bsa_employee,
                self.support_employee,
                self.bsa_manager,
                self.second_bsa_manager,
                self.support_manager,
            },
        )

    def test_head_cannot_assign_another_head_or_administrator(self):
        users = get_assignable_users(
            user=self.head,
        )

        self.assertNotIn(self.second_head, users)
        self.assertNotIn(self.administrator, users)
        self.assertNotIn(self.second_administrator, users)

    def test_administrator_can_assign_manager_and_employee(self):
        users = set(
            get_assignable_users(
                user=self.administrator,
            )
        )

        self.assertEqual(
            users,
            {
                self.bsa_employee,
                self.second_bsa_employee,
                self.support_employee,
                self.bsa_manager,
                self.second_bsa_manager,
                self.support_manager,
            },
        )

    def test_administrator_cannot_assign_administrator(self):
        users = get_assignable_users(
            user=self.administrator,
        )

        self.assertNotIn(self.administrator, users)
        self.assertNotIn(self.second_administrator, users)

    def test_inactive_users_are_not_assignable(self):
        users = get_assignable_users(
            user=self.head,
        )

        self.assertNotIn(self.inactive_employee, users)

    def test_task_reassignment_is_limited_to_task_department(self):
        users = set(
            get_assignable_users(
                user=self.head,
                task=self.task,
            )
        )

        self.assertEqual(
            users,
            {
                self.head,
                self.bsa_employee,
                self.second_bsa_employee,
                self.bsa_manager,
                self.second_bsa_manager,
            },
        )

        self.assertNotIn(self.support_employee, users)
        self.assertNotIn(self.support_manager, users)

    def test_current_assignee_remains_available_after_department_transfer(self):
        self.bsa_employee.department = self.support_department
        self.bsa_employee.save(update_fields=["department"])

        users = get_assignable_users(
            user=self.bsa_manager,
            task=self.task,
        )

        self.assertIn(self.bsa_employee, users)

    def test_current_assignee_remains_available_after_role_change(self):
        self.bsa_employee.role = self.administrator_role
        self.bsa_employee.save(update_fields=["role"])

        users = get_assignable_users(
            user=self.bsa_manager,
            task=self.task,
        )

        self.assertIn(self.bsa_employee, users)

    def test_manager_popup_form_uses_assignable_users_queryset(self):
        form = TaskPopupCreateForm(
            user=self.bsa_manager,
        )

        users = set(form.fields["assignee"].queryset)

        self.assertEqual(
            users,
            {
                self.bsa_manager,
                self.bsa_employee,
                self.second_bsa_employee,
            },
        )

    def test_manager_task_form_uses_task_department_queryset(self):
        form = TaskForm(
            instance=self.task,
            user=self.bsa_manager,
        )

        users = set(form.fields["assignee"].queryset)

        self.assertIn(self.bsa_employee, users)
        self.assertIn(self.second_bsa_employee, users)
        self.assertIn(self.bsa_manager, users)
        self.assertNotIn(self.support_employee, users)

    def test_manager_inline_form_uses_task_department_queryset(self):
        form = TaskInlineEditForm(
            instance=self.task,
            user=self.bsa_manager,
        )

        users = set(form.fields["assignee"].queryset)

        self.assertIn(self.bsa_employee, users)
        self.assertIn(self.second_bsa_employee, users)
        self.assertIn(self.bsa_manager, users)
        self.assertNotIn(self.support_employee, users)

    def test_employee_forms_do_not_contain_assignee_field(self):
        create_form = TaskForm(
            user=self.bsa_employee,
        )
        popup_form = TaskPopupCreateForm(
            user=self.bsa_employee,
        )
        inline_form = TaskInlineEditForm(
            instance=self.task,
            user=self.bsa_employee,
        )

        self.assertNotIn("assignee", create_form.fields)
        self.assertNotIn("assignee", popup_form.fields)
        self.assertNotIn("assignee", inline_form.fields)

    def test_employee_forms_do_not_contain_department_field(self):
        create_form = TaskForm(
            user=self.bsa_employee,
        )
        popup_form = TaskPopupCreateForm(
            user=self.bsa_employee,
        )
        inline_form = TaskInlineEditForm(
            instance=self.task,
            user=self.bsa_employee,
        )

        self.assertNotIn("department", create_form.fields)
        self.assertNotIn("department", popup_form.fields)
        self.assertNotIn("department", inline_form.fields)

    def test_manager_popup_and_inline_forms_do_not_contain_department_field(self):
        popup_form = TaskPopupCreateForm(
            user=self.bsa_manager,
        )
        inline_form = TaskInlineEditForm(
            instance=self.task,
            user=self.bsa_manager,
        )

        self.assertNotIn("department", popup_form.fields)
        self.assertNotIn("department", inline_form.fields)
        self.assertIn("assignee", popup_form.fields)
        self.assertIn("assignee", inline_form.fields)

    def test_head_popup_and_inline_forms_contain_department_and_assignee(self):
        popup_form = TaskPopupCreateForm(
            user=self.head,
        )
        inline_form = TaskInlineEditForm(
            instance=self.task,
            user=self.head,
        )

        self.assertIn("department", popup_form.fields)
        self.assertIn("assignee", popup_form.fields)
        self.assertIn("department", inline_form.fields)
        self.assertIn("assignee", inline_form.fields)


    def test_administrator_popup_and_inline_forms_contain_department_and_assignee(self):
        popup_form = TaskPopupCreateForm(
            user=self.administrator,
        )
        inline_form = TaskInlineEditForm(
            instance=self.task,
            user=self.administrator,
        )

        self.assertIn("department", popup_form.fields)
        self.assertIn("assignee", popup_form.fields)
        self.assertIn("department", inline_form.fields)
        self.assertIn("assignee", inline_form.fields)

    def test_head_inline_form_uses_selected_department_from_post_data(self):
        prefix = f"task-edit-{self.task.id}"

        form = TaskInlineEditForm(
            data={
                f"{prefix}-project_stream": self.project_stream.id,
                f"{prefix}-external_number": "",
                f"{prefix}-external_url": "",
                f"{prefix}-department": self.support_department.id,
                f"{prefix}-summary": self.task.summary,
                f"{prefix}-assignee": self.support_employee.id,
            },
            instance=self.task,
            user=self.head,
            prefix=prefix,
        )

        users = set(form.fields["assignee"].queryset)

        self.assertIn(self.support_employee, users)
        self.assertIn(self.support_manager, users)
        self.assertNotIn(self.bsa_employee, users)

    def test_head_remains_assignable_when_another_department_is_selected(self):
        users = get_assignable_users(
            user=self.head,
            department=self.support_department,
        )

        self.assertIn(self.head, users)
        self.assertIn(self.support_employee, users)
        self.assertIn(self.support_manager, users)

        self.assertNotIn(self.bsa_employee, users)
        self.assertNotIn(self.bsa_manager, users)
        self.assertNotIn(self.second_head, users)
        self.assertNotIn(self.administrator, users) 

    def test_administrator_assignable_users_are_filtered_by_selected_department(self):
        users = get_assignable_users(
            user=self.administrator,
            department=self.support_department,
        )

        self.assertEqual(
            set(users),
            {
                self.support_employee,
                self.support_manager,
            },
        )

    def test_inline_form_accepts_matching_department_and_assignee(self):
        prefix = f"task-edit-{self.task.id}"

        form = TaskInlineEditForm(
            data={
                f"{prefix}-project_stream": self.project_stream.id,
                f"{prefix}-external_number": "",
                f"{prefix}-external_url": "",
                f"{prefix}-department": self.support_department.id,
                f"{prefix}-summary": self.task.summary,
                f"{prefix}-assignee": self.support_employee.id,
            },
            instance=self.task,
            user=self.head,
            prefix=prefix,
        )

        self.assertTrue(form.is_valid(), form.errors)


    def test_inline_form_rejects_assignee_from_another_department(self):
        prefix = f"task-edit-{self.task.id}"

        form = TaskInlineEditForm(
            data={
                f"{prefix}-project_stream": self.project_stream.id,
                f"{prefix}-external_number": "",
                f"{prefix}-external_url": "",
                f"{prefix}-department": self.support_department.id,
                f"{prefix}-summary": self.task.summary,
                f"{prefix}-assignee": self.bsa_employee.id,
            },
            instance=self.task,
            user=self.head,
            prefix=prefix,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("assignee", form.errors)


class TrackerAccessTests(TestCase):
    def setUp(self):
        self.department = get_bsa_department()
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )

        self.employee = User.objects.create(
            login="test_employee",
            name="Test Employee",
            role=self.employee_role,
            department=self.department,
        )
        self.employee.set_password("test-password-123")
        self.employee.save()

        self.administrator_role, _ = Role.objects.get_or_create(
            code="administrator",
            defaults={"name": "Administrator"},
        )

        self.administrator = User.objects.create(
            login="test_administrator",
            name="Test Administrator",
            role=self.administrator_role,
            department=self.department,
        )
        self.administrator.set_password("test-password-123")
        self.administrator.save()

    def test_anonymous_user_is_redirected_from_dashboard(self):
        response = self.client.get(reverse("tracker:dashboard"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_authenticated_employee_can_open_dashboard(self):
        self.client.force_login(self.employee)

        response = self.client.get(reverse("tracker:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "tracker/dashboard.html")
        self.assertContains(response, "Рабочая область")

    def test_employee_cannot_open_administration_page(self):
        self.client.force_login(self.employee)

        response = self.client.get(reverse("tracker:administration"))

        self.assertEqual(response.status_code, 403)

    def test_administrator_can_open_administration_page(self):
        self.client.force_login(self.administrator)

        response = self.client.get(reverse("tracker:administration"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "tracker/administration.html")
        self.assertContains(response, "Администрирование")


class RoleRequiredDecoratorTests(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()

        @role_required("administrator")
        def protected_view(request):
            return HttpResponse("Allowed")

        self.protected_view = protected_view

    def test_anonymous_user_is_redirected_to_login(self):
        request = self.request_factory.get("/protected-page/")
        request.user = SimpleNamespace(
            is_authenticated=False,
        )

        response = self.protected_view(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)
        self.assertIn("next=/protected-page/", response.url)

    def test_user_without_role_gets_permission_denied(self):
        request = self.request_factory.get("/protected-page/")
        request.user = SimpleNamespace(
            is_authenticated=True,
            role=None,
        )

        with self.assertRaises(PermissionDenied):
            self.protected_view(request)

    def test_user_with_disallowed_role_gets_permission_denied(self):
        request = self.request_factory.get("/protected-page/")
        request.user = SimpleNamespace(
            is_authenticated=True,
            role=SimpleNamespace(code="employee"),
        )

        with self.assertRaises(PermissionDenied):
            self.protected_view(request)

    def test_user_with_allowed_role_can_open_view(self):
        request = self.request_factory.get("/protected-page/")
        request.user = SimpleNamespace(
            is_authenticated=True,
            role=SimpleNamespace(code="administrator"),
        )

        response = self.protected_view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"Allowed")


class WeekUtilsTests(TestCase):
    def test_monday_returns_same_date(self):
        self.assertEqual(
            get_week_start(date(2026, 7, 27)),
            date(2026, 7, 27),
        )

    def test_friday_returns_monday_of_same_week(self):
        self.assertEqual(
            get_week_start(date(2026, 7, 31)),
            date(2026, 7, 27),
        )

    def test_sunday_returns_monday_of_same_week(self):
        self.assertEqual(
            get_week_start(date(2026, 8, 2)),
            date(2026, 7, 27),
        )


class TaskModelsTests(TestCase):
    def setUp(self):
        self.department = get_bsa_department()
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )

        self.creator = User.objects.create(
            login="task_creator",
            name="Task Creator",
            role=self.employee_role,
            department=self.department,
        )
        self.creator.set_password("test-password-123")
        self.creator.save()

        self.assignee = User.objects.create(
            login="task_assignee",
            name="Task Assignee",
            role=self.employee_role,
            department=self.department,
        )
        self.assignee.set_password("test-password-123")
        self.assignee.save()

        self.project_stream = ProjectStream.objects.create(
            name="Пресеты",
            description="Задачи, связанные с пресетами.",
        )

        self.status = TaskStatus.objects.create(
            name="Новая",
            code="new",
            order=1,
            is_final=False,
            is_active=True,
        )

        self.task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Добавить управление пресетами",
            external_number="RND-1234",
            external_url="https://youtrack.example.com/issue/RND-1234",
            assignee=self.assignee,
            status=self.status,
            created_by=self.creator,
        )

    def test_project_stream_string_representation(self):
        self.assertEqual(
            str(self.project_stream),
            "Пресеты",
        )

    def test_task_status_string_representation(self):
        self.assertEqual(
            str(self.status),
            "Новая",
        )

    def test_task_string_representation_with_external_number(self):
        self.assertEqual(
            str(self.task),
            "RND-1234: Добавить управление пресетами",
        )

    def test_task_string_representation_without_external_number(self):
        task_without_number = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Проанализировать текущие настройки",
            assignee=self.assignee,
            status=self.status,
            created_by=self.creator,
        )

        self.assertEqual(
            str(task_without_number),
            "Проанализировать текущие настройки",
        )

    def test_external_number_and_url_can_be_empty(self):
        task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Задача без номера в YouTrack",
            assignee=self.assignee,
            status=self.status,
            created_by=self.creator,
        )

        self.assertEqual(task.external_number, "")
        self.assertEqual(task.external_url, "")

    def test_task_is_connected_to_project_status_and_users(self):
        self.assertEqual(
            self.task.project_stream,
            self.project_stream,
        )
        self.assertEqual(
            self.task.status,
            self.status,
        )
        self.assertEqual(
            self.task.assignee,
            self.assignee,
        )
        self.assertEqual(
            self.task.created_by,
            self.creator,
        )

    def test_reverse_relations_return_tasks(self):
        self.assertIn(
            self.task,
            self.project_stream.tasks.all(),
        )
        self.assertIn(
            self.task,
            self.status.tasks.all(),
        )
        self.assertIn(
            self.task,
            self.assignee.assigned_tasks.all(),
        )
        self.assertIn(
            self.task,
            self.creator.created_tasks.all(),
        )

    def test_task_created_and_updated_dates_are_filled_automatically(self):
        self.assertIsNotNone(self.task.created_at)
        self.assertIsNotNone(self.task.updated_at)

    def test_artifact_is_connected_to_task(self):
        artifact = TaskArtifact.objects.create(
            task=self.task,
            name="Требования",
            url="https://docs.example.com/task-requirements",
            created_by=self.creator,
        )

        self.assertEqual(artifact.task, self.task)
        self.assertEqual(artifact.created_by, self.creator)
        self.assertIn(
            artifact,
            self.task.artifacts.all(),
        )

    def test_artifact_string_representation(self):
        artifact = TaskArtifact.objects.create(
            task=self.task,
            name="API-документация",
            url="https://confluence.example.com/api-documentation",
            created_by=self.creator,
        )

        self.assertEqual(
            str(artifact),
            "API-документация",
        )

    def test_artifact_dates_are_filled_automatically(self):
        artifact = TaskArtifact.objects.create(
            task=self.task,
            name="Прототип",
            url="https://figma.example.com/task-prototype",
            created_by=self.creator,
        )

        self.assertIsNotNone(artifact.created_at)
        self.assertIsNotNone(artifact.updated_at)

    def test_deleting_task_also_deletes_its_artifacts(self):
        artifact = TaskArtifact.objects.create(
            task=self.task,
            name="Прототип",
            url="https://figma.example.com/task-prototype",
            created_by=self.creator,
        )

        artifact_id = artifact.id

        self.task.delete()

        self.assertFalse(
            TaskArtifact.objects.filter(id=artifact_id).exists()
        )

    def test_project_stream_used_by_task_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.project_stream.delete()

    def test_status_used_by_task_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.status.delete()

    def test_assignee_used_by_task_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.assignee.delete()

    def test_creator_used_by_task_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.creator.delete()

    def test_project_streams_are_ordered_by_name(self):
        ProjectStream.objects.create(
            name="Product Unit",
        )

        project_streams = list(
            ProjectStream.objects.values_list("name", flat=True)
        )

        self.assertEqual(
            project_streams,
            ["Product Unit", "Пресеты"],
        )

    def test_task_statuses_are_ordered_by_order(self):
        second_status = TaskStatus.objects.create(
            name="В работе",
            code="in_progress",
            order=2,
        )

        statuses = list(TaskStatus.objects.all())

        self.assertEqual(
            statuses,
            [self.status, second_status],
        )

    def test_weekly_status_is_connected_to_task_and_user(self):
        weekly_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 27),
            text="Проведён анализ требований.",
            updated_by=self.assignee,
        )

        self.assertEqual(weekly_status.task, self.task)
        self.assertEqual(weekly_status.updated_by, self.assignee)
        self.assertEqual(
            weekly_status.week_start,
            date(2026, 7, 27),
        )
        self.assertEqual(
            weekly_status.text,
            "Проведён анализ требований.",
        )
        self.assertIn(
            weekly_status,
            self.task.weekly_statuses.all(),
        )

    def test_weekly_status_string_representation(self):
        weekly_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 27),
            text="Статус текущей недели.",
            updated_by=self.assignee,
        )

        self.assertEqual(
            str(weekly_status),
            (
                "RND-1234: Добавить управление пресетами "
                "— неделя с 2026-07-27"
            ),
        )

    def test_weekly_status_dates_are_filled_automatically(self):
        weekly_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 27),
            text="Статус текущей недели.",
            updated_by=self.assignee,
        )

        self.assertIsNotNone(weekly_status.created_at)
        self.assertIsNotNone(weekly_status.updated_at)

    def test_task_can_have_weekly_statuses_for_different_weeks(self):
        first_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 20),
            text="Статус предыдущей недели.",
            updated_by=self.assignee,
        )

        second_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 27),
            text="Статус текущей недели.",
            updated_by=self.assignee,
        )

        self.assertEqual(
            TaskWeeklyStatus.objects.filter(task=self.task).count(),
            2,
        )
        self.assertIn(
            first_status,
            self.task.weekly_statuses.all(),
        )
        self.assertIn(
            second_status,
            self.task.weekly_statuses.all(),
        )

    def test_task_cannot_have_two_statuses_for_same_week(self):
        TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 27),
            text="Первый статус.",
            updated_by=self.assignee,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TaskWeeklyStatus.objects.create(
                    task=self.task,
                    week_start=date(2026, 7, 27),
                    text="Второй статус.",
                    updated_by=self.assignee,
                )

    def test_deleting_task_also_deletes_weekly_statuses(self):
        weekly_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 27),
            text="Статус для удаляемой задачи.",
            updated_by=self.assignee,
        )

        weekly_status_id = weekly_status.id

        self.task.delete()

        self.assertFalse(
            TaskWeeklyStatus.objects.filter(
                id=weekly_status_id,
            ).exists()
        )

    def test_weekly_statuses_are_ordered_from_newest_week(self):
        older_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 20),
            text="Старая неделя.",
            updated_by=self.assignee,
        )

        newer_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 27),
            text="Новая неделя.",
            updated_by=self.assignee,
        )

        weekly_statuses = list(
            TaskWeeklyStatus.objects.filter(task=self.task)
        )

        self.assertEqual(
            weekly_statuses,
            [newer_status, older_status],
        )


class TaskListViewTests(TestCase):
    def setUp(self):
        self.department = get_bsa_department()
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )

        self.manager_role, _ = Role.objects.get_or_create(
            code="manager",
            defaults={"name": "Manager"},
        )

        self.administrator_role, _ = Role.objects.get_or_create(
            code="administrator",
            defaults={"name": "Administrator"},
        )

        self.user = User.objects.create(
            login="task_list_user",
            name="Task List User",
            role=self.employee_role,
            department=self.department,
        )
        self.user.set_password("test-password-123")
        self.user.save()

        self.second_employee = User.objects.create(
            login="second_task_list_user",
            name="Second Task List User",
            role=self.employee_role,
            department=self.department,
        )
        self.second_employee.set_password("test-password-123")
        self.second_employee.save()

        self.employee_without_tasks = User.objects.create(
            login="employee_without_tasks",
            name="Employee Without Tasks",
            role=self.employee_role,
            department=self.department,
        )
        self.employee_without_tasks.set_password("test-password-123")
        self.employee_without_tasks.save()

        self.manager = User.objects.create(
            login="task_list_manager",
            name="Task List Manager",
            role=self.manager_role,
            department=self.department,
        )
        self.manager.set_password("test-password-123")
        self.manager.save()

        self.administrator = User.objects.create(
            login="task_list_administrator",
            name="Task List Administrator",
            role=self.administrator_role,
            department=self.department,
        )
        self.administrator.set_password("test-password-123")
        self.administrator.save()

        self.project_stream = ProjectStream.objects.create(
            name="Пресеты",
        )

        self.status = TaskStatus.objects.create(
            name="Новая",
            code="new",
            order=1,
            is_final=False,
            is_active=True,
        )

        self.done_status = TaskStatus.objects.create(
            name="Завершена",
            code="done",
            order=6,
            is_final=True,
            is_active=True,
        )

        self.cancelled_status = TaskStatus.objects.create(
            name="Отменена",
            code="cancelled",
            order=7,
            is_final=True,
            is_active=True,
        )

        self.task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Добавить страницу управления пресетами",
            external_number="RND-1234",
            external_url="https://youtrack.example.com/issue/RND-1234",
            assignee=self.user,
            status=self.status,
            created_by=self.user,
        )

        self.second_task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Задача другого сотрудника",
            external_number="RND-5678",
            external_url="https://youtrack.example.com/issue/RND-5678",
            assignee=self.second_employee,
            status=self.status,
            created_by=self.manager,
        )

        self.second_project_stream = ProjectStream.objects.create(
            name="Автоматизация",
        )

        self.done_task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Завершённая задача",
            external_number="RND-3000",
            assignee=self.user,
            status=self.done_status,
            created_by=self.user,
        )

        self.cancelled_task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Отменённая задача",
            external_number="RND-4000",
            assignee=self.user,
            status=self.cancelled_status,
            created_by=self.user,
        )

        self.sorting_task = Task.objects.create(
            project_stream=self.second_project_stream,
            department=self.department,
            summary="Анализ автоматизации",
            external_number="RND-0001",
            assignee=self.user,
            status=self.status,
            created_by=self.user,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_authenticated_user_can_open_task_list(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "tracker/task_list.html",
        )

    def test_task_list_contains_task_information(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(response, "RND-1234")
        self.assertContains(
            response,
            "Добавить страницу управления пресетами",
        )
        self.assertContains(response, "Пресеты")
        self.assertContains(response, "Task List User")
        self.assertContains(response, "Новая")

    def test_employee_sees_assigned_task(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(
            response,
            "Добавить страницу управления пресетами",
        )
        self.assertContains(response, "RND-1234")

    def test_employee_does_not_see_task_assigned_to_another_employee(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertNotContains(
            response,
            "Задача другого сотрудника",
        )
        self.assertNotContains(response, "RND-5678")

    def test_employee_task_queryset_contains_only_assigned_tasks(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        tasks = list(response.context["tasks"])

        self.assertEqual(
            set(tasks),
            {
                self.task,
                self.sorting_task,
            },
        )

    def test_manager_sees_all_tasks(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(
            response,
            "Добавить страницу управления пресетами",
        )
        self.assertContains(
            response,
            "Задача другого сотрудника",
        )
        self.assertContains(response, "RND-1234")
        self.assertContains(response, "RND-5678")

        self.assertEqual(
            set(response.context["tasks"]),
            {
                self.task,
                self.second_task,
                self.sorting_task,
            },
        )

    def test_administrator_sees_all_tasks(self):
        self.client.force_login(self.administrator)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(
            response,
            "Добавить страницу управления пресетами",
        )
        self.assertContains(
            response,
            "Задача другого сотрудника",
        )
        self.assertContains(response, "RND-1234")
        self.assertContains(response, "RND-5678")

        self.assertEqual(
            set(response.context["tasks"]),
            {
                self.task,
                self.second_task,
                self.sorting_task,
            },
        )

    def test_employee_without_assigned_tasks_sees_empty_list_message(self):
        self.client.force_login(self.employee_without_tasks)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertEqual(list(response.context["tasks"]), [])
        self.assertContains(response, "Задач пока нет.")

    def test_task_number_contains_external_link(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(
            response,
            'href="https://youtrack.example.com/issue/RND-1234"',
        )

    def test_task_number_without_url_is_displayed_as_text(self):
        self.task.external_url = ""
        self.task.save()

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(response, "RND-1234")
        self.assertNotContains(
            response,
            'href="https://youtrack.example.com/issue/RND-1234"',
        )

    def test_task_without_external_number_displays_dash(self):
        self.task.external_number = ""
        self.task.external_url = ""
        self.task.save()

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(response, "—")

    def test_empty_task_list_displays_message(self):
        Task.objects.all().delete()

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(response, "Задач пока нет.")


    def test_final_tasks_are_hidden_by_default(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        tasks = set(response.context["tasks"])

        self.assertIn(self.task, tasks)
        self.assertIn(self.sorting_task, tasks)
        self.assertNotIn(self.done_task, tasks)
        self.assertNotIn(self.cancelled_task, tasks)

        self.assertFalse(response.context["show_done"])
        self.assertFalse(response.context["show_cancelled"])

    def test_done_tasks_can_be_shown(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"show_done": "1"},
        )

        tasks = set(response.context["tasks"])

        self.assertIn(self.task, tasks)
        self.assertIn(self.sorting_task, tasks)
        self.assertIn(self.done_task, tasks)
        self.assertNotIn(self.cancelled_task, tasks)

        self.assertTrue(response.context["show_done"])
        self.assertFalse(response.context["show_cancelled"])

    def test_cancelled_tasks_can_be_shown(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"show_cancelled": "1"},
        )

        tasks = set(response.context["tasks"])

        self.assertIn(self.task, tasks)
        self.assertIn(self.sorting_task, tasks)
        self.assertNotIn(self.done_task, tasks)
        self.assertIn(self.cancelled_task, tasks)

        self.assertFalse(response.context["show_done"])
        self.assertTrue(response.context["show_cancelled"])

    def test_all_final_tasks_can_be_shown(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {
                "show_done": "1",
                "show_cancelled": "1",
            },
        )

        tasks = set(response.context["tasks"])

        self.assertEqual(
            tasks,
            {
                self.task,
                self.sorting_task,
                self.done_task,
                self.cancelled_task,
            },
        )

        self.assertTrue(response.context["show_done"])
        self.assertTrue(response.context["show_cancelled"])

    def test_show_done_requires_value_one(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"show_done": "yes"},
        )

        self.assertNotIn(
            self.done_task,
            response.context["tasks"],
        )
        self.assertFalse(response.context["show_done"])

    def test_tasks_are_sorted_by_project_ascending_by_default(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        tasks = list(response.context["tasks"])

        self.assertEqual(
            tasks,
            [
                self.sorting_task,
                self.task,
            ],
        )
        self.assertEqual(
            response.context["selected_sort"],
            "project",
        )
        self.assertEqual(
            response.context["sort_direction"],
            "asc",
        )

    def test_tasks_can_be_sorted_by_project_descending(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {
                "sort": "project",
                "direction": "desc",
            },
        )

        self.assertEqual(
            list(response.context["tasks"]),
            [
                self.task,
                self.sorting_task,
            ],
        )

    def test_tasks_can_be_sorted_by_number_ascending(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {
                "sort": "number",
                "direction": "asc",
            },
        )

        self.assertEqual(
            list(response.context["tasks"]),
            [
                self.sorting_task,
                self.task,
            ],
        )
        self.assertEqual(
            response.context["selected_sort"],
            "number",
        )

    def test_tasks_can_be_sorted_by_number_descending(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {
                "sort": "number",
                "direction": "desc",
            },
        )

        self.assertEqual(
            list(response.context["tasks"]),
            [
                self.task,
                self.sorting_task,
            ],
        )

    def test_tasks_can_be_sorted_by_summary_ascending(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {
                "sort": "summary",
                "direction": "asc",
            },
        )

        self.assertEqual(
            list(response.context["tasks"]),
            [
                self.sorting_task,
                self.task,
            ],
        )
        self.assertEqual(
            response.context["selected_sort"],
            "summary",
        )

    def test_tasks_can_be_sorted_by_summary_descending(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {
                "sort": "summary",
                "direction": "desc",
            },
        )

        self.assertEqual(
            list(response.context["tasks"]),
            [
                self.task,
                self.sorting_task,
            ],
        )

    def test_invalid_sort_value_falls_back_to_project(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"sort": "unknown"},
        )

        self.assertEqual(
            list(response.context["tasks"]),
            [
                self.sorting_task,
                self.task,
            ],
        )
        self.assertEqual(
            response.context["selected_sort"],
            "project",
        )

    def test_invalid_direction_falls_back_to_ascending(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {
                "sort": "project",
                "direction": "sideways",
            },
        )

        self.assertEqual(
            list(response.context["tasks"]),
            [
                self.sorting_task,
                self.task,
            ],
        )
        self.assertEqual(
            response.context["sort_direction"],
            "asc",
        )

    def create_pagination_tasks(
        self,
        count,
        *,
        assignee=None,
        summary_prefix="Задача пагинации",
    ):
        assignee = assignee or self.user

        return Task.objects.bulk_create(
            [
                Task(
                    project_stream=self.project_stream,
                    department=self.department,
                    summary=f"{summary_prefix} {index:02d}",
                    external_number=f"PAG-{index:02d}",
                    assignee=assignee,
                    status=self.status,
                    created_by=self.manager,
                )
                for index in range(count)
            ]
        )

    def test_task_list_is_paginated_by_ten_tasks(self):
        self.create_pagination_tasks(9)
        self.client.force_login(self.user)

        first_page = self.client.get(
            reverse("tracker:task-list")
        )
        second_page = self.client.get(
            reverse("tracker:task-list"),
            {"page": "2"},
        )

        self.assertEqual(len(first_page.context["tasks"]), 10)
        self.assertEqual(len(second_page.context["tasks"]), 1)
        self.assertEqual(
            first_page.context["page_obj"].paginator.num_pages,
            2,
        )
        self.assertEqual(second_page.context["page_obj"].number, 2)

    def test_access_filtering_is_applied_before_pagination(self):
        self.create_pagination_tasks(
            10,
            assignee=self.second_employee,
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertEqual(
            set(response.context["tasks"]),
            {self.task, self.sorting_task},
        )
        self.assertEqual(
            response.context["page_obj"].paginator.num_pages,
            1,
        )

    def test_search_filters_the_full_queryset_before_pagination(self):
        self.create_pagination_tasks(10)
        matching_task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Особая задача с маркером needle",
            external_number="PAG-TARGET",
            assignee=self.user,
            status=self.status,
            created_by=self.manager,
        )
        self.client.force_login(self.user)

        unfiltered_second_page = self.client.get(
            reverse("tracker:task-list"),
            {"page": "2"},
        )
        response = self.client.get(
            reverse("tracker:task-list"),
            {"search": "needle"},
        )

        self.assertIn(
            matching_task,
            unfiltered_second_page.context["tasks"],
        )
        self.assertEqual(
            list(response.context["tasks"]),
            [matching_task],
        )
        self.assertEqual(response.context["selected_search"], "needle")

    def test_search_finds_tasks_by_assignee_name(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"search": "Second Task List"},
        )

        self.assertEqual(
            list(response.context["tasks"]),
            [self.second_task],
        )

    def test_sorting_is_applied_before_pagination(self):
        self.create_pagination_tasks(9)
        self.client.force_login(self.user)

        first_page = self.client.get(
            reverse("tracker:task-list"),
            {"sort": "number", "direction": "desc"},
        )
        second_page = self.client.get(
            reverse("tracker:task-list"),
            {
                "sort": "number",
                "direction": "desc",
                "page": "2",
            },
        )

        actual_ids = [
            task.id
            for task in (
                list(first_page.context["tasks"])
                + list(second_page.context["tasks"])
            )
        ]
        expected_ids = list(
            Task.objects.filter(assignee=self.user)
            .exclude(status__code__in=["done", "cancelled"])
            .order_by("-external_number", "id")
            .values_list("id", flat=True)
        )

        self.assertEqual(actual_ids, expected_ids)

    def test_status_toggles_are_applied_before_pagination(self):
        self.create_pagination_tasks(8)
        self.client.force_login(self.user)

        default_response = self.client.get(
            reverse("tracker:task-list")
        )
        with_done_response = self.client.get(
            reverse("tracker:task-list"),
            {"show_done": "1"},
        )

        self.assertEqual(
            default_response.context["page_obj"].paginator.num_pages,
            1,
        )
        self.assertEqual(
            with_done_response.context["page_obj"].paginator.num_pages,
            2,
        )

    def test_pagination_control_preserves_list_settings(self):
        self.create_pagination_tasks(
            11,
            summary_prefix="Общий маркер",
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {
                "search": "Общий маркер",
                "sort": "number",
                "direction": "desc",
                "show_done": "1",
            },
        )

        self.assertContains(response, 'class="pagination-control"')
        self.assertContains(response, "1 / 2")
        self.assertContains(response, "search=%D0%9E%D0%B1%D1%89%D0%B8%D0%B9")
        self.assertContains(response, "sort=number")
        self.assertContains(response, "direction=desc")
        self.assertContains(response, "show_done=1")
        self.assertContains(response, "page=2")

    def test_pagination_control_is_hidden_for_single_page(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertNotContains(response, 'class="pagination-control"')

    def test_list_control_changes_reset_page_in_browser_url(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(
            response,
            'url.searchParams.delete("page");',
            count=2,
        )

    def test_search_is_submitted_by_form_without_input_debounce(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(response, 'class="search-button"')
        self.assertContains(response, "Поиск")
        self.assertContains(
            response,
            'taskListControls.addEventListener("submit"',
        )
        self.assertNotContains(
            response,
            'searchInput.addEventListener("input"',
        )

    def test_search_clear_resets_filter_and_search_regains_focus(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"search": "RND-1234"},
        )

        self.assertContains(
            response,
            'searchInput.addEventListener("search"',
        )
        self.assertContains(response, 'searchParams.has(')
        self.assertContains(
            response,
            'name === "search" && !value.trim()',
        )
        self.assertContains(response, 'window.sessionStorage.setItem(')
        self.assertContains(response, "restoreSearchFocus();")
        self.assertContains(response, "searchInput.focus();")

    def test_employee_does_not_see_other_users_final_tasks(self):
        other_done_task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Чужая завершённая задача",
            external_number="RND-9999",
            assignee=self.second_employee,
            status=self.done_status,
            created_by=self.second_employee,
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"show_done": "1"},
        )

        tasks = set(response.context["tasks"])

        self.assertIn(self.done_task, tasks)
        self.assertNotIn(other_done_task, tasks)


    @patch("tracker.views.timezone.localdate")
    def test_task_list_context_contains_current_and_previous_weeks(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertEqual(
            response.context["current_week_start"],
            date(2026, 7, 27),
        )
        self.assertEqual(
            response.context["previous_week_start"],
            date(2026, 7, 20),
        )
        self.assertEqual(
            response.context["older_week_start"],
            date(2026, 7, 13),
        )
        self.assertEqual(
            response.context["newer_week_start"],
            date(2026, 7, 27),
        )
        self.assertFalse(response.context["can_move_forward"])

    @patch("tracker.views.timezone.localdate")
    def test_task_list_attaches_current_and_previous_statuses_to_task(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)

        current_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 27),
            text="Статус текущей недели.",
            updated_by=self.user,
        )
        previous_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 20),
            text="Статус предыдущей недели.",
            updated_by=self.user,
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        task = next(
            task
            for task in response.context["tasks"]
            if task.id == self.task.id
        )

        self.assertEqual(
            task.current_weekly_status,
            current_status,
        )
        self.assertEqual(
            task.previous_weekly_status,
            previous_status,
        )
        self.assertEqual(
            task.weekly_status_form.instance,
            current_status,
        )

    @patch("tracker.views.timezone.localdate")
    def test_employee_does_not_receive_other_task_weekly_statuses(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)

        other_status = TaskWeeklyStatus.objects.create(
            task=self.second_task,
            week_start=date(2026, 7, 27),
            text="Чужой еженедельный статус.",
            updated_by=self.second_employee,
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        tasks = response.context["tasks"]

        self.assertEqual(
            set(tasks),
            {
                self.task,
                self.sorting_task,
            },
        )

        for task in tasks:
            self.assertNotEqual(
                task.current_weekly_status,
                other_status,
            )

    @patch("tracker.views.timezone.localdate")
    def test_employee_can_create_current_weekly_status(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("tracker:task-list"),
            {
                "task_id": self.task.id,
                f"task-{self.task.id}-text": (
                    "Подготовлен проект решения."
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        weekly_status = TaskWeeklyStatus.objects.get(
            task=self.task,
            week_start=date(2026, 7, 27),
        )

        self.assertEqual(
            weekly_status.text,
            "Подготовлен проект решения.",
        )
        self.assertEqual(weekly_status.updated_by, self.user)

    @patch("tracker.views.timezone.localdate")
    def test_second_post_updates_existing_weekly_status(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)

        weekly_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 27),
            text="Исходный статус.",
            updated_by=self.user,
        )

        self.client.force_login(self.user)

        response = self.client.post(
            reverse("tracker:task-list"),
            {
                "task_id": self.task.id,
                f"task-{self.task.id}-text": (
                    "Обновлённый статус."
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )
        self.assertEqual(
            TaskWeeklyStatus.objects.filter(
                task=self.task,
                week_start=date(2026, 7, 27),
            ).count(),
            1,
        )

        weekly_status.refresh_from_db()

        self.assertEqual(
            weekly_status.text,
            "Обновлённый статус.",
        )
        self.assertEqual(weekly_status.updated_by, self.user)

    @patch("tracker.views.timezone.localdate")
    def test_employee_cannot_save_status_for_another_users_task(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("tracker:task-list"),
            {
                "task_id": self.second_task.id,
                f"task-{self.second_task.id}-text": (
                    "Попытка изменить чужой статус."
                ),
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(
            TaskWeeklyStatus.objects.filter(
                task=self.second_task,
            ).exists()
        )

    @patch("tracker.views.timezone.localdate")
    def test_manager_can_save_status_for_any_task(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("tracker:task-list"),
            {
                "task_id": self.second_task.id,
                f"task-{self.second_task.id}-text": (
                    "Статус обновлён менеджером."
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        weekly_status = TaskWeeklyStatus.objects.get(
            task=self.second_task,
            week_start=date(2026, 7, 27),
        )

        self.assertEqual(
            weekly_status.text,
            "Статус обновлён менеджером.",
        )
        self.assertEqual(weekly_status.updated_by, self.manager)

    @patch("tracker.views.timezone.localdate")
    def test_week_query_selects_requested_previous_week(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)

        selected_status = TaskWeeklyStatus.objects.create(
            task=self.task,
            week_start=date(2026, 7, 13),
            text="Статус выбранной прошлой недели.",
            updated_by=self.user,
        )

        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"week": "2026-07-13"},
        )

        task = next(
            task
            for task in response.context["tasks"]
            if task.id == self.task.id
        )

        self.assertEqual(
            response.context["previous_week_start"],
            date(2026, 7, 13),
        )
        self.assertEqual(
            task.previous_weekly_status,
            selected_status,
        )
        self.assertEqual(
            response.context["newer_week_start"],
            date(2026, 7, 20),
        )
        self.assertTrue(response.context["can_move_forward"])

    @patch("tracker.views.timezone.localdate")
    def test_current_or_future_week_query_falls_back_to_previous_week(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"week": "2026-08-03"},
        )

        self.assertEqual(
            response.context["previous_week_start"],
            date(2026, 7, 20),
        )
        self.assertFalse(response.context["can_move_forward"])

    @patch("tracker.views.timezone.localdate")
    def test_invalid_week_query_falls_back_to_previous_week(
        self,
        mocked_localdate,
    ):
        mocked_localdate.return_value = date(2026, 7, 30)
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("tracker:task-list"),
            {"week": "not-a-date"},
        )

        self.assertEqual(
            response.context["previous_week_start"],
            date(2026, 7, 20),
        )


class TaskInlineUpdateTests(TestCase):
    def setUp(self):
        self.department = get_bsa_department()
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )
        self.manager_role, _ = Role.objects.get_or_create(
            code="manager",
            defaults={"name": "Manager"},
        )

        self.employee = User.objects.create(
            login="inline_edit_employee",
            name="Inline Edit Employee",
            role=self.employee_role,
            department=self.department,
        )
        self.employee.set_password("test-password-123")
        self.employee.save()

        self.other_employee = User.objects.create(
            login="inline_edit_other_employee",
            name="Inline Edit Other Employee",
            role=self.employee_role,
            department=self.department,
        )
        self.other_employee.set_password("test-password-123")
        self.other_employee.save()

        self.manager = User.objects.create(
            login="inline_edit_manager",
            name="Inline Edit Manager",
            role=self.manager_role,
            department=self.department,
        )
        self.manager.set_password("test-password-123")
        self.manager.save()

        self.project_stream = ProjectStream.objects.create(
            name="Исходный стрим",
        )
        self.second_project_stream = ProjectStream.objects.create(
            name="Новый стрим",
        )

        self.status = TaskStatus.objects.create(
            name="Новая",
            code="new",
            order=1,
        )
        self.second_status = TaskStatus.objects.create(
            name="В работе",
            code="in_progress",
            order=2,
        )

        self.task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Исходное описание",
            external_number="RND-1000",
            external_url=(
                "https://youtrack.example.com/issue/RND-1000"
            ),
            assignee=self.employee,
            status=self.status,
            created_by=self.employee,
        )

        self.other_task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Задача другого сотрудника",
            external_number="RND-2000",
            external_url=(
                "https://youtrack.example.com/issue/RND-2000"
            ),
            assignee=self.other_employee,
            status=self.status,
            created_by=self.other_employee,
        )
        self.other_department = Department.objects.create(
            code="inline_support",
            name="Inline Support",
            is_active=True,
        )

        self.head_role, _ = Role.objects.get_or_create(
            code="head",
            defaults={"name": "Head"},
        )

        self.administrator_role, _ = Role.objects.get_or_create(
            code="administrator",
            defaults={"name": "Administrator"},
        )

        self.other_department_employee = User.objects.create(
            login="inline_support_employee",
            name="Inline Support Employee",
            role=self.employee_role,
            department=self.other_department,
        )

        self.head = User.objects.create(
            login="inline_head",
            name="Inline Head",
            role=self.head_role,
            department=self.department,
        )

        self.administrator = User.objects.create(
            login="inline_administrator",
            name="Inline Administrator",
            role=self.administrator_role,
            department=self.department,
        )

    def get_inline_form_data(
        self,
        task,
        *,
        project_stream=None,
        summary=None,
        external_number=None,
        external_url=None,
        department=None,
        assignee=None,
        status=None,
    ):
        prefix = f"task-edit-{task.id}"

        data = {
            f"{prefix}-project_stream": (
                project_stream or task.project_stream
            ).id,
            f"{prefix}-summary": (
                summary
                if summary is not None
                else task.summary
            ),
            f"{prefix}-external_number": (
                external_number
                if external_number is not None
                else task.external_number
            ),
            f"{prefix}-external_url": (
                external_url
                if external_url is not None
                else task.external_url
            ),
            f"{prefix}-assignee": (
                assignee or task.assignee
            ).id,
        }

        if status is not None:
            data[f"{prefix}-status"] = status.id

        if department is not None:
            data[f"{prefix}-department"] = department.id

        return data

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.task.id],
            ),
            self.get_inline_form_data(self.task),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("accounts:login"),
            response.url,
        )

    def test_employee_can_inline_update_own_task_but_cannot_change_assignee(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.task.id],
            ),
            self.get_inline_form_data(
                self.task,
                project_stream=self.second_project_stream,
                summary="Обновлённое описание",
                external_number="RND-3000",
                external_url=(
                    "https://youtrack.example.com/issue/RND-3000"
                ),
                assignee=self.other_employee,
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(
            data["task"]["project_stream"]["name"],
            "Новый стрим",
        )
        self.assertEqual(
            data["task"]["external_number"],
            "RND-3000",
        )
        self.assertEqual(
            data["task"]["external_url"],
            "https://youtrack.example.com/issue/RND-3000",
        )
        self.assertEqual(
            data["task"]["summary"],
            "Обновлённое описание",
        )
        self.assertEqual(
            data["task"]["assignee"]["name"],
            "Inline Edit Employee",
        )

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.project_stream,
            self.second_project_stream,
        )
        self.assertEqual(
            self.task.summary,
            "Обновлённое описание",
        )
        self.assertEqual(
            self.task.external_number,
            "RND-3000",
        )
        self.assertEqual(
            self.task.external_url,
            "https://youtrack.example.com/issue/RND-3000",
        )
        self.assertEqual(
            self.task.assignee,
            self.employee,
        )

    def test_employee_cannot_inline_update_other_users_task(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.other_task.id],
            ),
            self.get_inline_form_data(
                self.other_task,
                summary="Попытка изменить чужую задачу",
            ),
        )

        self.assertEqual(response.status_code, 403)

        self.other_task.refresh_from_db()

        self.assertEqual(
            self.other_task.summary,
            "Задача другого сотрудника",
        )

    def test_invalid_inline_form_returns_json_errors(self):
        self.client.force_login(self.employee)

        prefix = f"task-edit-{self.task.id}"

        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.task.id],
            ),
            {
                f"{prefix}-project_stream": "",
                f"{prefix}-summary": "",
                f"{prefix}-external_number": "RND-1000",
                f"{prefix}-external_url": "not-a-valid-url",
                f"{prefix}-assignee": "",
            },
        )

        self.assertEqual(response.status_code, 400)

        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("project_stream", data["errors"])
        self.assertIn("summary", data["errors"])
        self.assertIn("external_url", data["errors"])
        self.assertNotIn("assignee", data["errors"])

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.summary,
            "Исходное описание",
        )

    def test_inline_update_does_not_change_task_status(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.task.id],
            ),
            self.get_inline_form_data(
                self.task,
                summary="Описание изменено",
                status=self.second_status,
            ),
        )

        self.assertEqual(response.status_code, 200)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.summary,
            "Описание изменено",
        )
        self.assertEqual(
            self.task.status,
            self.status,
        )

    def test_manager_can_inline_update_any_task(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.other_task.id],
            ),
            self.get_inline_form_data(
                self.other_task,
                summary="Задача изменена менеджером",
            ),
        )

        self.assertEqual(response.status_code, 200)

        self.other_task.refresh_from_db()

        self.assertEqual(
            self.other_task.summary,
            "Задача изменена менеджером",
        )

    def test_inline_update_requires_post(self):
        self.client.force_login(self.employee)

        response = self.client.get(
            reverse(
                "tracker:task-inline-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 405)

    def test_employee_cannot_change_department_via_crafted_inline_post(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.task.id],
            ),
            self.get_inline_form_data(
                self.task,
                summary="Описание изменено сотрудником",
                department=self.other_department,
            ),
        )

        self.assertEqual(response.status_code, 200)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.department,
            self.department,
        )
        self.assertEqual(
            self.task.assignee,
            self.employee,
        )

    def test_manager_cannot_change_department_via_crafted_inline_post(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.task.id],
            ),
            self.get_inline_form_data(
                self.task,
                summary="Описание изменено менеджером",
                department=self.other_department,
            ),
        )

        self.assertEqual(response.status_code, 200)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.department,
            self.department,
        )

    def test_head_can_move_task_to_another_department_and_assign_to_self(self):
        self.client.force_login(self.head)

        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.task.id],
            ),
            self.get_inline_form_data(
                self.task,
                department=self.other_department,
                assignee=self.head,
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.department,
            self.other_department,
        )
        self.assertEqual(
            self.task.assignee,
            self.head,
        )

        # Технический отдел Head не меняется.
        self.assertEqual(
            self.head.department,
            self.department,
        )

    def test_head_cannot_move_task_to_another_department_with_wrong_assignee(self):
        self.client.force_login(self.head)

        response = self.client.post(
            reverse(
                "tracker:task-inline-update",
                args=[self.task.id],
            ),
            self.get_inline_form_data(
                self.task,
                department=self.other_department,
                assignee=self.employee,
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 400)

        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("assignee", data["errors"])

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.department,
            self.department,
        )
        self.assertEqual(
            self.task.assignee,
            self.employee,
        )

class TaskStatusUpdateTests(TestCase):
    def setUp(self):
        self.department = get_bsa_department()
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )
        self.manager_role, _ = Role.objects.get_or_create(
            code="manager",
            defaults={"name": "Manager"},
        )

        self.employee = User.objects.create(
            login="status_update_employee",
            name="Status Update Employee",
            role=self.employee_role,
            department=self.department,
        )
        self.employee.set_password("test-password-123")
        self.employee.save()

        self.other_employee = User.objects.create(
            login="status_update_other_employee",
            name="Status Update Other Employee",
            role=self.employee_role,
            department=self.department,
        )
        self.other_employee.set_password("test-password-123")
        self.other_employee.save()

        self.manager = User.objects.create(
            login="status_update_manager",
            name="Status Update Manager",
            role=self.manager_role,
            department=self.department,
        )
        self.manager.set_password("test-password-123")
        self.manager.save()

        self.project_stream = ProjectStream.objects.create(
            name="Стрим статусов",
        )

        self.initial_status = TaskStatus.objects.create(
            name="Новая",
            code="new",
            order=1,
            is_active=True,
        )
        self.active_status = TaskStatus.objects.create(
            name="В работе",
            code="in_progress",
            order=2,
            is_active=True,
        )
        self.inactive_status = TaskStatus.objects.create(
            name="Архивный статус",
            code="archived",
            order=3,
            is_active=False,
        )

        self.task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Задача сотрудника",
            external_number="RND-5000",
            external_url=(
                "https://youtrack.example.com/issue/RND-5000"
            ),
            assignee=self.employee,
            status=self.initial_status,
            created_by=self.employee,
        )

        self.other_task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Задача другого сотрудника",
            external_number="RND-6000",
            external_url=(
                "https://youtrack.example.com/issue/RND-6000"
            ),
            assignee=self.other_employee,
            status=self.initial_status,
            created_by=self.other_employee,
        )

    def get_status_form_data(self, task, status):
        prefix = f"task-status-{task.id}"

        return {
            f"{prefix}-status": status.id,
        }

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.post(
            reverse(
                "tracker:task-status-update",
                args=[self.task.id],
            ),
            self.get_status_form_data(
                self.task,
                self.active_status,
            ),
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("accounts:login"),
            response.url,
        )

    def test_employee_can_update_status_of_own_task(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-status-update",
                args=[self.task.id],
            ),
            self.get_status_form_data(
                self.task,
                self.active_status,
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(
            data["status"]["id"],
            self.active_status.id,
        )
        self.assertEqual(
            data["status"]["name"],
            "В работе",
        )
        self.assertEqual(
            data["status"]["code"],
            "in_progress",
        )
        self.assertFalse(data["status"]["is_final"])

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            self.active_status,
        )

    def test_status_update_does_not_change_other_task_fields(self):
        original_summary = self.task.summary
        original_project_stream = self.task.project_stream
        original_assignee = self.task.assignee
        original_external_number = self.task.external_number
        original_external_url = self.task.external_url

        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-status-update",
                args=[self.task.id],
            ),
            {
                **self.get_status_form_data(
                    self.task,
                    self.active_status,
                ),
                "summary": "Попытка изменить описание",
                "project_stream": 999999,
                "assignee": self.other_employee.id,
                "external_number": "RND-9999",
                "external_url": (
                    "https://youtrack.example.com/issue/RND-9999"
                ),
            },
        )

        self.assertEqual(response.status_code, 200)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            self.active_status,
        )
        self.assertEqual(
            self.task.summary,
            original_summary,
        )
        self.assertEqual(
            self.task.project_stream,
            original_project_stream,
        )
        self.assertEqual(
            self.task.assignee,
            original_assignee,
        )
        self.assertEqual(
            self.task.external_number,
            original_external_number,
        )
        self.assertEqual(
            self.task.external_url,
            original_external_url,
        )

    def test_employee_cannot_update_status_of_other_users_task(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-status-update",
                args=[self.other_task.id],
            ),
            self.get_status_form_data(
                self.other_task,
                self.active_status,
            ),
        )

        self.assertEqual(response.status_code, 403)

        self.other_task.refresh_from_db()

        self.assertEqual(
            self.other_task.status,
            self.initial_status,
        )

    def test_manager_can_update_status_of_any_task(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "tracker:task-status-update",
                args=[self.other_task.id],
            ),
            self.get_status_form_data(
                self.other_task,
                self.active_status,
            ),
        )

        self.assertEqual(response.status_code, 200)

        self.other_task.refresh_from_db()

        self.assertEqual(
            self.other_task.status,
            self.active_status,
        )

    def test_inactive_status_is_rejected(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-status-update",
                args=[self.task.id],
            ),
            self.get_status_form_data(
                self.task,
                self.inactive_status,
            ),
        )

        self.assertEqual(response.status_code, 400)

        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("status", data["errors"])

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            self.initial_status,
        )

    def test_missing_status_returns_validation_error(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-status-update",
                args=[self.task.id],
            ),
            {},
        )

        self.assertEqual(response.status_code, 400)

        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("status", data["errors"])

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.status,
            self.initial_status,
        )

    def test_status_update_requires_post(self):
        self.client.force_login(self.employee)

        response = self.client.get(
            reverse(
                "tracker:task-status-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 405)


class TaskArtifactAjaxTests(TestCase):
    def setUp(self):
        self.department = get_bsa_department()
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )
        self.manager_role, _ = Role.objects.get_or_create(
            code="manager",
            defaults={"name": "Manager"},
        )

        self.employee = User.objects.create(
            login="artifact_employee",
            name="Artifact Employee",
            role=self.employee_role,
            department=self.department,
        )
        self.employee.set_password("test-password-123")
        self.employee.save()

        self.other_employee = User.objects.create(
            login="artifact_other_employee",
            name="Artifact Other Employee",
            role=self.employee_role,
            department=self.department,
        )
        self.other_employee.set_password("test-password-123")
        self.other_employee.save()

        self.manager = User.objects.create(
            login="artifact_manager",
            name="Artifact Manager",
            role=self.manager_role,
            department=self.department,
        )
        self.manager.set_password("test-password-123")
        self.manager.save()

        self.project_stream = ProjectStream.objects.create(
            name="Артефакты",
        )
        self.status = TaskStatus.objects.create(
            name="Новая",
            code="new",
            order=1,
        )

        self.task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Задача сотрудника",
            assignee=self.employee,
            status=self.status,
            created_by=self.employee,
        )
        self.other_task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Задача другого сотрудника",
            assignee=self.other_employee,
            status=self.status,
            created_by=self.other_employee,
        )

    def test_employee_can_create_artifact_for_own_task(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-artifact-create",
                args=[self.task.id],
            ),
            {
                "name": "Требования",
                "url": "https://docs.example.com/requirements",
            },
        )

        self.assertEqual(response.status_code, 201)

        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(data["artifact"]["name"], "Требования")
        self.assertEqual(
            data["artifact"]["url"],
            "https://docs.example.com/requirements",
        )

        artifact = TaskArtifact.objects.get(
            id=data["artifact"]["id"],
        )

        self.assertEqual(artifact.task, self.task)
        self.assertEqual(artifact.created_by, self.employee)

    def test_invalid_artifact_form_returns_errors(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-artifact-create",
                args=[self.task.id],
            ),
            {
                "name": "",
                "url": "not-a-valid-url",
            },
        )

        self.assertEqual(response.status_code, 400)

        data = response.json()

        self.assertFalse(data["success"])
        self.assertIn("name", data["errors"])
        self.assertIn("url", data["errors"])
        self.assertEqual(TaskArtifact.objects.count(), 0)

    def test_employee_cannot_create_artifact_for_other_task(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-artifact-create",
                args=[self.other_task.id],
            ),
            {
                "name": "Чужой документ",
                "url": "https://docs.example.com/other",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(TaskArtifact.objects.count(), 0)

    def test_manager_can_create_artifact_for_any_task(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "tracker:task-artifact-create",
                args=[self.other_task.id],
            ),
            {
                "name": "Документ менеджера",
                "url": "https://docs.example.com/manager",
            },
        )

        self.assertEqual(response.status_code, 201)

        artifact = TaskArtifact.objects.get()

        self.assertEqual(artifact.task, self.other_task)
        self.assertEqual(artifact.created_by, self.manager)

    def test_employee_can_delete_artifact_from_own_task(self):
        artifact = TaskArtifact.objects.create(
            task=self.task,
            name="Артефакт для удаления",
            url="https://docs.example.com/delete",
            created_by=self.employee,
        )

        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-artifact-delete",
                args=[self.task.id, artifact.id],
            )
        )

        self.assertEqual(response.status_code, 200)

        data = response.json()

        self.assertTrue(data["success"])
        self.assertEqual(data["artifact_id"], artifact.id)
        self.assertFalse(
            TaskArtifact.objects.filter(id=artifact.id).exists()
        )

    def test_employee_cannot_delete_artifact_from_other_task(self):
        artifact = TaskArtifact.objects.create(
            task=self.other_task,
            name="Чужой артефакт",
            url="https://docs.example.com/other-delete",
            created_by=self.other_employee,
        )

        self.client.force_login(self.employee)

        response = self.client.post(
            reverse(
                "tracker:task-artifact-delete",
                args=[self.other_task.id, artifact.id],
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertTrue(
            TaskArtifact.objects.filter(id=artifact.id).exists()
        )

    def test_artifact_from_another_task_returns_404(self):
        artifact = TaskArtifact.objects.create(
            task=self.other_task,
            name="Артефакт другой задачи",
            url="https://docs.example.com/wrong-task",
            created_by=self.other_employee,
        )

        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "tracker:task-artifact-delete",
                args=[self.task.id, artifact.id],
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            TaskArtifact.objects.filter(id=artifact.id).exists()
        )

    def test_create_artifact_requires_post(self):
        self.client.force_login(self.employee)

        response = self.client.get(
            reverse(
                "tracker:task-artifact-create",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 405)

    def test_delete_artifact_requires_post(self):
        artifact = TaskArtifact.objects.create(
            task=self.task,
            name="Артефакт",
            url="https://docs.example.com/artifact",
            created_by=self.employee,
        )

        self.client.force_login(self.employee)

        response = self.client.get(
            reverse(
                "tracker:task-artifact-delete",
                args=[self.task.id, artifact.id],
            )
        )

        self.assertEqual(response.status_code, 405)



class TaskCreateViewTests(TestCase):
    def setUp(self):
        self.department = get_bsa_department()
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )

        self.creator = User.objects.create(
            login="task_create_user",
            name="Task Create User",
            role=self.employee_role,
            department=self.department,
        )
        self.creator.set_password("test-password-123")
        self.creator.save()

        self.assignee = User.objects.create(
            login="task_create_assignee",
            name="Task Create Assignee",
            role=self.employee_role,
            department=self.department,
        )
        self.assignee.set_password("test-password-123")
        self.assignee.save()

        self.project_stream = ProjectStream.objects.create(
            name="Пресеты",
        )

        self.status = TaskStatus.objects.create(
            name="Новая",
            code="new",
            order=1,
            is_final=False,
            is_active=True,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse("tracker:task-create")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("accounts:login"),
            response.url,
        )

    def test_authenticated_user_can_open_task_create_page(self):
        self.client.force_login(self.creator)

        response = self.client.get(
            reverse("tracker:task-create")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "tracker/task_form.html",
        )
        self.assertContains(response, "Создание задачи")
        self.assertContains(response, "Создать задачу")

    def test_task_create_page_contains_expected_fields(self):
        self.client.force_login(self.creator)

        response = self.client.get(
            reverse("tracker:task-create")
        )

        self.assertContains(response, 'name="project_stream"')
        self.assertContains(response, 'name="summary"')
        self.assertContains(response, 'name="external_number"')
        self.assertContains(response, 'name="external_url"')
        self.assertNotContains(response, 'name="assignee"')
        self.assertContains(response, 'name="status"')

    def test_valid_form_creates_task(self):
        self.client.force_login(self.creator)

        response = self.client.post(
            reverse("tracker:task-create"),
            {
                "project_stream": self.project_stream.id,
                "summary": "Создать задачу через интерфейс",
                "external_number": "RND-9999",
                "external_url": (
                    "https://youtrack.example.com/issue/RND-9999"
                ),
                "assignee": self.assignee.id,
                "status": self.status.id,
                "artifacts-TOTAL_FORMS": "0",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertEqual(Task.objects.count(), 1)

        task = Task.objects.get()

        self.assertEqual(
            task.project_stream,
            self.project_stream,
        )
        self.assertEqual(
            task.summary,
            "Создать задачу через интерфейс",
        )
        self.assertEqual(
            task.external_number,
            "RND-9999",
        )
        self.assertEqual(
            task.external_url,
            "https://youtrack.example.com/issue/RND-9999",
        )
        self.assertEqual(
            task.assignee,
            self.creator,
        )
        self.assertEqual(
            task.department,
            self.creator.department,
        )
        self.assertEqual(
            task.status,
            self.status,
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

    def test_created_by_is_set_to_current_user(self):
        self.client.force_login(self.creator)

        self.client.post(
            reverse("tracker:task-create"),
            {
                "project_stream": self.project_stream.id,
                "summary": "Проверить автоматическое заполнение автора",
                "external_number": "",
                "external_url": "",
                "assignee": self.assignee.id,
                "status": self.status.id,
                "artifacts-TOTAL_FORMS": "0",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
            },
        )

        task = Task.objects.get()

        self.assertEqual(
            task.created_by,
            self.creator,
        )

    def test_task_can_be_created_without_external_number_and_url(self):
        self.client.force_login(self.creator)

        response = self.client.post(
            reverse("tracker:task-create"),
            {
                "project_stream": self.project_stream.id,
                "summary": "Задача без внешнего номера",
                "external_number": "",
                "external_url": "",
                "assignee": self.assignee.id,
                "status": self.status.id,
                "artifacts-TOTAL_FORMS": "0",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        task = Task.objects.get()

        self.assertEqual(
            task.department,
            self.creator.department,
        )
        self.assertEqual(task.external_number, "")
        self.assertEqual(task.external_url, "")

    def test_invalid_form_does_not_create_task(self):
        self.client.force_login(self.creator)

        response = self.client.post(
            reverse("tracker:task-create"),
            {
                "project_stream": "",
                "summary": "",
                "external_number": "RND-9999",
                "external_url": "not-a-valid-url",
                "assignee": "",
                "status": "",
                "artifacts-TOTAL_FORMS": "0",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "tracker/task_form.html",
        )
        self.assertEqual(Task.objects.count(), 0)
        self.assertTrue(response.context["form"].errors)

    def test_task_list_contains_create_task_popup(self):
        self.client.force_login(self.creator)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(response, 'id="create-task-button"')
        self.assertContains(response, 'id="create-task-modal"')
        self.assertContains(response, "Создать задачу")


    def test_task_create_page_contains_artifact_formset(self):
        self.client.force_login(self.creator)

        response = self.client.get(
            reverse("tracker:task-create")
        )

        self.assertContains(
            response,
            'name="artifacts-TOTAL_FORMS"',
        )
        self.assertContains(
            response,
            'name="artifacts-0-name"',
        )
        self.assertContains(
            response,
            'name="artifacts-0-url"',
        )
        self.assertContains(response, "Добавить артефакт")

    def test_task_can_be_created_with_artifact(self):
        self.client.force_login(self.creator)

        response = self.client.post(
            reverse("tracker:task-create"),
            {
                "project_stream": self.project_stream.id,
                "summary": "Задача с артефактом",
                "external_number": "RND-5000",
                "external_url": (
                    "https://youtrack.example.com/issue/RND-5000"
                ),
                "assignee": self.assignee.id,
                "status": self.status.id,
                "artifacts-TOTAL_FORMS": "1",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
                "artifacts-0-name": "Требования",
                "artifacts-0-url": (
                    "https://docs.example.com/requirements"
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )
        self.assertEqual(Task.objects.count(), 1)
        self.assertEqual(TaskArtifact.objects.count(), 1)

        task = Task.objects.get()
        artifact = TaskArtifact.objects.get()

        self.assertEqual(artifact.task, task)
        self.assertEqual(artifact.name, "Требования")
        self.assertEqual(
            artifact.url,
            "https://docs.example.com/requirements",
        )
        self.assertEqual(artifact.created_by, self.creator)

    def test_invalid_artifact_does_not_create_task(self):
        self.client.force_login(self.creator)

        response = self.client.post(
            reverse("tracker:task-create"),
            {
                "project_stream": self.project_stream.id,
                "summary": "Задача с некорректным артефактом",
                "external_number": "",
                "external_url": "",
                "assignee": self.assignee.id,
                "status": self.status.id,
                "artifacts-TOTAL_FORMS": "1",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
                "artifacts-0-name": "Документ",
                "artifacts-0-url": "not-a-valid-url",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Task.objects.count(), 0)
        self.assertEqual(TaskArtifact.objects.count(), 0)
        self.assertTrue(
            response.context["artifact_formset"].errors
        )

class TaskUpdateViewTests(TestCase):
    def setUp(self):
        self.department = get_bsa_department()
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )

        self.manager_role, _ = Role.objects.get_or_create(
            code="manager",
            defaults={"name": "Manager"},
        )

        self.administrator_role, _ = Role.objects.get_or_create(
            code="administrator",
            defaults={"name": "Administrator"},
        )

        self.creator = User.objects.create(
            login="task_update_creator",
            name="Task Update Creator",
            role=self.employee_role,
            department=self.department,
        )
        self.creator.set_password("test-password-123")
        self.creator.save()

        self.assignee = User.objects.create(
            login="task_update_assignee",
            name="Task Update Assignee",
            role=self.employee_role,
            department=self.department,
        )
        self.assignee.set_password("test-password-123")
        self.assignee.save()

        self.second_assignee = User.objects.create(
            login="task_update_second_assignee",
            name="Second Task Assignee",
            role=self.employee_role,
            department=self.department,
        )
        self.second_assignee.set_password("test-password-123")
        self.second_assignee.save()

        self.manager = User.objects.create(
            login="task_update_manager",
            name="Task Update Manager",
            role=self.manager_role,
            department=self.department,
        )
        self.manager.set_password("test-password-123")
        self.manager.save()

        self.administrator = User.objects.create(
            login="task_update_administrator",
            name="Task Update Administrator",
            role=self.administrator_role,
            department=self.department,
        )
        self.administrator.set_password("test-password-123")
        self.administrator.save()

        self.project_stream = ProjectStream.objects.create(
            name="Пресеты",
        )

        self.second_project_stream = ProjectStream.objects.create(
            name="Product Unit",
        )

        self.status = TaskStatus.objects.create(
            name="Новая",
            code="new",
            order=1,
            is_final=False,
            is_active=True,
        )

        self.second_status = TaskStatus.objects.create(
            name="В работе",
            code="in_progress",
            order=2,
            is_final=False,
            is_active=True,
        )

        self.task = Task.objects.create(
            project_stream=self.project_stream,
            department=self.department,
            summary="Исходное описание задачи",
            external_number="RND-1000",
            external_url=(
                "https://youtrack.example.com/issue/RND-1000"
            ),
            assignee=self.assignee,
            status=self.status,
            created_by=self.creator,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("accounts:login"),
            response.url,
        )

    def test_assignee_can_open_task_update_page(self):
        self.client.force_login(self.assignee)

        response = self.client.get(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "tracker/task_form.html",
        )
        self.assertContains(response, "Редактирование задачи")
        self.assertContains(response, "Сохранить изменения")

    def test_employee_cannot_open_another_employees_task(self):
        self.client.force_login(self.second_assignee)

        response = self.client.get(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_creator_cannot_open_task_when_not_assignee(self):
        self.client.force_login(self.creator)

        response = self.client.get(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_task_update_form_contains_current_task_values(self):
        self.client.force_login(self.assignee)

        response = self.client.get(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(
            response.context["form"].instance,
            self.task,
        )
        self.assertContains(
            response,
            "Исходное описание задачи",
        )
        self.assertContains(response, "RND-1000")
        self.assertContains(
            response,
            "https://youtrack.example.com/issue/RND-1000",
        )

    def test_assignee_can_update_own_task(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            ),
            {
                "project_stream": self.second_project_stream.id,
                "summary": "Обновлённое описание задачи",
                "external_number": "RND-2000",
                "external_url": (
                    "https://youtrack.example.com/issue/RND-2000"
                ),
                "assignee": self.second_assignee.id,
                "status": self.second_status.id,
                "artifacts-TOTAL_FORMS": "0",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
            },
        )

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.project_stream,
            self.second_project_stream,
        )
        self.assertEqual(
            self.task.summary,
            "Обновлённое описание задачи",
        )
        self.assertEqual(
            self.task.external_number,
            "RND-2000",
        )
        self.assertEqual(
            self.task.external_url,
            "https://youtrack.example.com/issue/RND-2000",
        )
        self.assertEqual(
            self.task.assignee,
            self.assignee,
        )
        self.assertEqual(
            self.task.status,
            self.second_status,
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

    def test_employee_cannot_update_another_employees_task_via_post(self):
        self.client.force_login(self.second_assignee)

        response = self.client.post(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            ),
            {
                "project_stream": self.second_project_stream.id,
                "summary": "Попытка изменить чужую задачу",
                "external_number": "RND-9999",
                "external_url": (
                    "https://youtrack.example.com/issue/RND-9999"
                ),
                "assignee": self.second_assignee.id,
                "status": self.second_status.id,
                "artifacts-TOTAL_FORMS": "0",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertEqual(response.status_code, 403)

        self.task.refresh_from_db()

        self.assertEqual(
            self.task.summary,
            "Исходное описание задачи",
        )
        self.assertEqual(
            self.task.external_number,
            "RND-1000",
        )
        self.assertEqual(
            self.task.project_stream,
            self.project_stream,
        )
        self.assertEqual(
            self.task.assignee,
            self.assignee,
        )
        self.assertEqual(
            self.task.status,
            self.status,
        )

    def test_manager_can_open_any_task(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "tracker/task_form.html",
        )

    def test_manager_can_update_any_task(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            ),
            {
                "project_stream": self.second_project_stream.id,
                "summary": "Задача изменена менеджером",
                "external_number": "RND-3000",
                "external_url": (
                    "https://youtrack.example.com/issue/RND-3000"
                ),
                "assignee": self.second_assignee.id,
                "status": self.second_status.id,
                "artifacts-TOTAL_FORMS": "0",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
            },
        )

        self.task.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.task.summary,
            "Задача изменена менеджером",
        )
        self.assertEqual(
            self.task.assignee,
            self.second_assignee,
        )
        self.assertEqual(
            self.task.status,
            self.second_status,
        )

    def test_administrator_can_open_any_task(self):
        self.client.force_login(self.administrator)

        response = self.client.get(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "tracker/task_form.html",
        )

    def test_administrator_can_update_any_task(self):
        self.client.force_login(self.administrator)

        response = self.client.post(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            ),
            {
                "project_stream": self.second_project_stream.id,
                "summary": "Задача изменена администратором",
                "external_number": "RND-4000",
                "external_url": (
                    "https://youtrack.example.com/issue/RND-4000"
                ),
                "assignee": self.second_assignee.id,
                "status": self.second_status.id,
                "artifacts-TOTAL_FORMS": "0",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
            },
        )

        self.task.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            self.task.summary,
            "Задача изменена администратором",
        )
        self.assertEqual(
            self.task.assignee,
            self.second_assignee,
        )
        self.assertEqual(
            self.task.status,
            self.second_status,
        )

    def test_updating_task_does_not_create_new_task(self):
        self.client.force_login(self.assignee)

        tasks_count_before_update = Task.objects.count()

        self.client.post(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            ),
            {
                "project_stream": self.project_stream.id,
                "summary": "Изменённая существующая задача",
                "external_number": "RND-1000",
                "external_url": (
                    "https://youtrack.example.com/issue/RND-1000"
                ),
                "assignee": self.assignee.id,
                "status": self.status.id,
                "artifacts-TOTAL_FORMS": "0",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
            },
        )

        self.assertEqual(
            Task.objects.count(),
            tasks_count_before_update,
        )

    def test_missing_task_returns_404(self):
        self.client.force_login(self.assignee)

        response = self.client.get(
            reverse(
                "tracker:task-update",
                args=[999999],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_task_list_contains_inline_edit_button(self):
        self.client.force_login(self.assignee)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        inline_update_url = reverse(
            "tracker:task-inline-update",
            args=[self.task.id],
        )

        self.assertContains(
            response,
            "data-task-edit",
        )
        self.assertContains(
            response,
            f'action="{inline_update_url}"',
        )
        self.assertContains(
            response,
            "data-task-edit-form",
        )


    def test_update_page_contains_existing_artifact(self):
        artifact = TaskArtifact.objects.create(
            task=self.task,
            name="Исходные требования",
            url="https://docs.example.com/original",
            created_by=self.creator,
        )

        self.client.force_login(self.assignee)

        response = self.client.get(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, artifact.name)
        self.assertContains(response, artifact.url)
        self.assertContains(
            response,
            f'value="{artifact.id}"',
        )

    def test_assignee_can_add_artifact_during_update(self):
        self.client.force_login(self.assignee)

        response = self.client.post(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            ),
            {
                "project_stream": self.project_stream.id,
                "summary": self.task.summary,
                "external_number": self.task.external_number,
                "external_url": self.task.external_url,
                "assignee": self.assignee.id,
                "status": self.status.id,
                "artifacts-TOTAL_FORMS": "1",
                "artifacts-INITIAL_FORMS": "0",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
                "artifacts-0-name": "Прототип",
                "artifacts-0-url": (
                    "https://figma.example.com/prototype"
                ),
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        artifact = TaskArtifact.objects.get()

        self.assertEqual(artifact.task, self.task)
        self.assertEqual(artifact.name, "Прототип")
        self.assertEqual(artifact.created_by, self.assignee)

    def test_assignee_can_update_existing_artifact(self):
        artifact = TaskArtifact.objects.create(
            task=self.task,
            name="Старое название",
            url="https://docs.example.com/old",
            created_by=self.creator,
        )

        self.client.force_login(self.assignee)

        response = self.client.post(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            ),
            {
                "project_stream": self.project_stream.id,
                "summary": self.task.summary,
                "external_number": self.task.external_number,
                "external_url": self.task.external_url,
                "assignee": self.assignee.id,
                "status": self.status.id,
                "artifacts-TOTAL_FORMS": "1",
                "artifacts-INITIAL_FORMS": "1",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
                "artifacts-0-id": artifact.id,
                "artifacts-0-task": self.task.id,
                "artifacts-0-name": "Новое название",
                "artifacts-0-url": "https://docs.example.com/new",
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        artifact.refresh_from_db()

        self.assertEqual(artifact.name, "Новое название")
        self.assertEqual(
            artifact.url,
            "https://docs.example.com/new",
        )
        self.assertEqual(artifact.created_by, self.creator)

    def test_assignee_can_delete_existing_artifact(self):
        artifact = TaskArtifact.objects.create(
            task=self.task,
            name="Артефакт для удаления",
            url="https://docs.example.com/delete",
            created_by=self.creator,
        )

        self.client.force_login(self.assignee)

        response = self.client.post(
            reverse(
                "tracker:task-update",
                args=[self.task.id],
            ),
            {
                "project_stream": self.project_stream.id,
                "summary": self.task.summary,
                "external_number": self.task.external_number,
                "external_url": self.task.external_url,
                "assignee": self.assignee.id,
                "status": self.status.id,
                "artifacts-TOTAL_FORMS": "1",
                "artifacts-INITIAL_FORMS": "1",
                "artifacts-MIN_NUM_FORMS": "0",
                "artifacts-MAX_NUM_FORMS": "1000",
                "artifacts-0-id": artifact.id,
                "artifacts-0-task": self.task.id,
                "artifacts-0-name": artifact.name,
                "artifacts-0-url": artifact.url,
                "artifacts-0-DELETE": "on",
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )
        self.assertFalse(
            TaskArtifact.objects.filter(id=artifact.id).exists()
        )
        self.assertTrue(Task.objects.filter(id=self.task.id).exists())

class TaskPopupCreateTests(TestCase):
    def setUp(self):
        self.department = get_bsa_department()
        self.other_department = Department.objects.create(
            code="support_popup",
            name="Support Popup",
            is_active=True,
        )
        self.employee_role, _ = Role.objects.get_or_create(code="employee", defaults={"name": "Employee"})
        self.manager_role, _ = Role.objects.get_or_create(code="manager", defaults={"name": "Manager"})
        self.administrator_role, _ = Role.objects.get_or_create(code="administrator", defaults={"name": "Administrator"})
        self.head_role, _ = Role.objects.get_or_create(
            code="head",
            defaults={"name": "Head"},
        )
        self.employee = User.objects.create(login="popup_employee", name="Popup Employee", role=self.employee_role, department=self.department)
        self.other_employee = User.objects.create(login="popup_other", name="Popup Other", role=self.employee_role, department=self.department)
        self.manager = User.objects.create(login="popup_manager", name="Popup Manager", role=self.manager_role, department=self.department)
        self.administrator = User.objects.create(login="popup_admin", name="Popup Admin", role=self.administrator_role, department=self.department)
        self.other_department_employee = User.objects.create(
            login="popup_support_employee",
            name="Popup Support Employee",
            role=self.employee_role,
            department=self.other_department,
        )

        self.other_department_manager = User.objects.create(
            login="popup_support_manager",
            name="Popup Support Manager",
            role=self.manager_role,
            department=self.other_department,
        )

        self.head = User.objects.create(
            login="popup_head",
            name="Popup Head",
            role=self.head_role,
            department=self.department,
        )
        self.project_stream = ProjectStream.objects.create(name="Попап")
        self.new_status = TaskStatus.objects.create(name="Новая", code="new", order=1, is_active=True)
        self.other_status = TaskStatus.objects.create(name="В работе", code="in_progress", order=2, is_active=True)

    def create_data(self, **overrides):
        data = {
            "action": "create_task",
            "project_stream": self.project_stream.id,
            "summary": "Задача из попапа",
            "external_number": "RND-7777",
            "external_url": "https://youtrack.example.com/issue/RND-7777",
            "assignee": self.other_employee.id,
            "status": self.other_status.id,
        }
        data.update(overrides)
        return data

    def test_employee_popup_does_not_render_assignee_select(self):
        self.client.force_login(self.employee)
        response = self.client.get(reverse("tracker:task-list"))
        self.assertContains(response, 'id="create-task-modal"')
        self.assertNotIn(
            "assignee",
            response.context["create_form"].fields,
        )
        self.assertNotContains(
            response,
            '<select name="assignee"',
        )
        self.assertContains(response, "Popup Employee")

    def test_employee_creates_task_assigned_to_self_in_new_status(self):
        self.client.force_login(self.employee)
        response = self.client.post(reverse("tracker:task-list"), self.create_data())
        task = Task.objects.get(summary="Задача из попапа")
        self.assertEqual(task.assignee, self.employee)
        self.assertEqual(task.created_by, self.employee)
        self.assertEqual(task.status, self.new_status)
        self.assertRedirects(response, reverse("tracker:task-list"))
        self.assertEqual(
            task.department,
            self.employee.department,
        )

    def test_manager_can_choose_assignee(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("tracker:task-list"), self.create_data())
        task = Task.objects.get(summary="Задача из попапа")
        self.assertEqual(task.assignee, self.other_employee)
        self.assertEqual(task.status, self.new_status)
        self.assertEqual(
            task.department,
            self.other_employee.department,
        )

    def test_administrator_can_choose_assignee(self):
        self.client.force_login(self.administrator)
        self.client.post(reverse("tracker:task-list"), self.create_data())
        task = Task.objects.get(summary="Задача из попапа")
        self.assertEqual(task.assignee, self.other_employee)
        self.assertEqual(task.status, self.new_status)
        self.assertEqual(
            task.department,
            self.other_employee.department,
        )

    def test_create_redirect_preserves_list_query_string(self):
        self.client.force_login(self.manager)
        url = reverse("tracker:task-list") + "?sort=number&direction=desc&show_done=1"
        response = self.client.post(url, self.create_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, url)

    def test_invalid_popup_form_reopens_modal(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("tracker:task-list"), self.create_data(project_stream="", summary=""))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["open_create_modal"])
        self.assertTrue(response.context["create_form"].errors)
        self.assertEqual(Task.objects.count(), 0)

    def test_employee_inline_edit_cannot_change_assignee(self):
        task = Task.objects.create(project_stream=self.project_stream, department=self.department, summary="Своя задача", assignee=self.employee, status=self.new_status, created_by=self.employee)
        self.client.force_login(self.employee)
        prefix = f"task-edit-{task.id}"
        response = self.client.post(
            reverse("tracker:task-inline-update", args=[task.id]),
            {
                f"{prefix}-project_stream": self.project_stream.id,
                f"{prefix}-summary": "Обновленная задача",
                f"{prefix}-external_number": "",
                f"{prefix}-external_url": "",
                f"{prefix}-assignee": self.other_employee.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.assignee, self.employee)
        self.assertEqual(task.summary, "Обновленная задача")

    def test_employee_popup_does_not_render_department_select(self):
        self.client.force_login(self.employee)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertNotIn(
            "department",
            response.context["create_form"].fields,
        )
        self.assertNotContains(
            response,
            '<select name="department"',
        )

    def test_employee_cannot_spoof_department_or_assignee_in_popup(self):
        self.client.force_login(self.employee)

        response = self.client.post(
            reverse("tracker:task-list"),
            self.create_data(
                department=self.other_department.id,
                assignee=self.other_department_employee.id,
            ),
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        task = Task.objects.get(
            summary="Задача из попапа"
        )

        self.assertEqual(task.assignee, self.employee)
        self.assertEqual(task.department, self.department)

    def test_manager_popup_does_not_render_department_select(self):
        self.client.force_login(self.manager)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertNotIn(
            "department",
            response.context["create_form"].fields,
        )
        self.assertIn(
            "assignee",
            response.context["create_form"].fields,
        )

    def test_manager_cannot_spoof_department_in_popup(self):
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("tracker:task-list"),
            self.create_data(
                department=self.other_department.id,
                assignee=self.other_employee.id,
            ),
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        task = Task.objects.get(
            summary="Задача из попапа"
        )

        self.assertEqual(task.assignee, self.other_employee)
        self.assertEqual(task.department, self.department)

    def test_head_can_create_task_in_another_department_assigned_to_self(self):
        self.client.force_login(self.head)

        response = self.client.post(
            reverse("tracker:task-list"),
            self.create_data(
                department=self.other_department.id,
                assignee=self.head.id,
            ),
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        task = Task.objects.get(
            summary="Задача из попапа"
        )

        self.assertEqual(task.assignee, self.head)
        self.assertEqual(
            task.department,
            self.other_department,
        )

        # Технический отдел самого Head при этом остаётся BSA.
        self.assertEqual(
            self.head.department,
            self.department,
        )

    def test_head_can_create_task_for_employee_of_selected_department(self):
        self.client.force_login(self.head)

        response = self.client.post(
            reverse("tracker:task-list"),
            self.create_data(
                department=self.other_department.id,
                assignee=self.other_department_employee.id,
            ),
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        task = Task.objects.get(
            summary="Задача из попапа"
        )

        self.assertEqual(
            task.department,
            self.other_department,
        )
        self.assertEqual(
            task.assignee,
            self.other_department_employee,
        )

    def test_head_cannot_create_task_with_assignee_from_another_department(self):
        self.client.force_login(self.head)

        response = self.client.post(
            reverse("tracker:task-list"),
            self.create_data(
                department=self.other_department.id,
                assignee=self.other_employee.id,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            response.context["open_create_modal"]
        )
        self.assertIn(
            "assignee",
            response.context["create_form"].errors,
        )
        self.assertEqual(Task.objects.count(), 0)

    def test_administrator_cannot_create_task_with_assignee_from_another_department(self):
        self.client.force_login(self.administrator)

        response = self.client.post(
            reverse("tracker:task-list"),
            self.create_data(
                department=self.other_department.id,
                assignee=self.other_employee.id,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "assignee",
            response.context["create_form"].errors,
        )
        self.assertEqual(Task.objects.count(), 0)

    def test_administrator_cannot_assign_task_to_self(self):
        self.client.force_login(self.administrator)

        response = self.client.post(
            reverse("tracker:task-list"),
            self.create_data(
                department=self.department.id,
                assignee=self.administrator.id,
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "assignee",
            response.context["create_form"].errors,
        )
        self.assertEqual(Task.objects.count(), 0)
