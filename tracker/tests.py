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

from accounts.models import Role, User
from tracker.decorators import role_required
from tracker.models import (
    ProjectStream,
    Task,
    TaskArtifact,
    TaskStatus,
    TaskWeeklyStatus,
)


class TrackerAccessTests(TestCase):
    def setUp(self):
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )

        self.employee = User.objects.create(
            login="test_employee",
            name="Test Employee",
            role=self.employee_role,
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
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )

        self.creator = User.objects.create(
            login="task_creator",
            name="Task Creator",
            role=self.employee_role,
        )
        self.creator.set_password("test-password-123")
        self.creator.save()

        self.assignee = User.objects.create(
            login="task_assignee",
            name="Task Assignee",
            role=self.employee_role,
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
        )
        self.user.set_password("test-password-123")
        self.user.save()

        self.second_employee = User.objects.create(
            login="second_task_list_user",
            name="Second Task List User",
            role=self.employee_role,
        )
        self.second_employee.set_password("test-password-123")
        self.second_employee.save()

        self.employee_without_tasks = User.objects.create(
            login="employee_without_tasks",
            name="Employee Without Tasks",
            role=self.employee_role,
        )
        self.employee_without_tasks.set_password("test-password-123")
        self.employee_without_tasks.save()

        self.manager = User.objects.create(
            login="task_list_manager",
            name="Task List Manager",
            role=self.manager_role,
        )
        self.manager.set_password("test-password-123")
        self.manager.save()

        self.administrator = User.objects.create(
            login="task_list_administrator",
            name="Task List Administrator",
            role=self.administrator_role,
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

        self.task = Task.objects.create(
            project_stream=self.project_stream,
            summary="Добавить страницу управления пресетами",
            external_number="RND-1234",
            external_url="https://youtrack.example.com/issue/RND-1234",
            assignee=self.user,
            status=self.status,
            created_by=self.user,
        )

        self.second_task = Task.objects.create(
            project_stream=self.project_stream,
            summary="Задача другого сотрудника",
            external_number="RND-5678",
            external_url="https://youtrack.example.com/issue/RND-5678",
            assignee=self.second_employee,
            status=self.status,
            created_by=self.manager,
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

        self.assertEqual(tasks, [self.task])

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
            {self.task, self.second_task},
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
            {self.task, self.second_task},
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

        task = response.context["tasks"][0]

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

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0], self.task)
        self.assertNotEqual(
            tasks[0].current_weekly_status,
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

        task = response.context["tasks"][0]

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



class TaskArtifactAjaxTests(TestCase):
    def setUp(self):
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
        )
        self.employee.set_password("test-password-123")
        self.employee.save()

        self.other_employee = User.objects.create(
            login="artifact_other_employee",
            name="Artifact Other Employee",
            role=self.employee_role,
        )
        self.other_employee.set_password("test-password-123")
        self.other_employee.save()

        self.manager = User.objects.create(
            login="artifact_manager",
            name="Artifact Manager",
            role=self.manager_role,
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
            summary="Задача сотрудника",
            assignee=self.employee,
            status=self.status,
            created_by=self.employee,
        )
        self.other_task = Task.objects.create(
            project_stream=self.project_stream,
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
        self.employee_role, _ = Role.objects.get_or_create(
            code="employee",
            defaults={"name": "Employee"},
        )

        self.creator = User.objects.create(
            login="task_create_user",
            name="Task Create User",
            role=self.employee_role,
        )
        self.creator.set_password("test-password-123")
        self.creator.save()

        self.assignee = User.objects.create(
            login="task_create_assignee",
            name="Task Create Assignee",
            role=self.employee_role,
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
        self.assertContains(response, 'name="assignee"')
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
            self.assignee,
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

    def test_task_list_contains_create_task_link(self):
        self.client.force_login(self.creator)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        self.assertContains(
            response,
            f'href="{reverse("tracker:task-create")}"',
        )
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
        )
        self.creator.set_password("test-password-123")
        self.creator.save()

        self.assignee = User.objects.create(
            login="task_update_assignee",
            name="Task Update Assignee",
            role=self.employee_role,
        )
        self.assignee.set_password("test-password-123")
        self.assignee.save()

        self.second_assignee = User.objects.create(
            login="task_update_second_assignee",
            name="Second Task Assignee",
            role=self.employee_role,
        )
        self.second_assignee.set_password("test-password-123")
        self.second_assignee.save()

        self.manager = User.objects.create(
            login="task_update_manager",
            name="Task Update Manager",
            role=self.manager_role,
        )
        self.manager.set_password("test-password-123")
        self.manager.save()

        self.administrator = User.objects.create(
            login="task_update_administrator",
            name="Task Update Administrator",
            role=self.administrator_role,
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
            self.second_assignee,
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

    def test_task_list_contains_edit_link(self):
        self.client.force_login(self.assignee)

        response = self.client.get(
            reverse("tracker:task-list")
        )

        task_update_url = reverse(
            "tracker:task-update",
            args=[self.task.id],
        )

        self.assertContains(
            response,
            f'href="{task_update_url}"',
        )
        self.assertContains(response, "Редактировать")


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