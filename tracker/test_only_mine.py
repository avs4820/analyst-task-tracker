from django.test import TestCase
from django.urls import reverse

from accounts.models import Department, Role, User
from tracker.models import Task
from tracker import tests as fixtures


class OnlyMineTests(TestCase):
    setUp = fixtures.TaskListViewTests.setUp

    def get_list(self, user, **params):
        self.client.force_login(user)
        return self.client.get(reverse("tracker:task-list"), params)

    def assign_to(self, task, user):
        task.assignee = user
        task.save(update_fields=["assignee"])

    def test_manager_default_and_explicit_values(self):
        self.assign_to(self.task, self.manager)
        for params in ({}, {"only_mine": "1"}, {"only_mine": "invalid"}):
            with self.subTest(params=params):
                response = self.get_list(self.manager, **params)
                self.assertEqual(response.context["tasks"], [self.task])
                self.assertTrue(response.context["only_mine"])
                self.assertContains(response, "Только свои")
        response = self.get_list(self.manager, only_mine="0")
        self.assertEqual(set(response.context["tasks"]), {
            self.task, self.second_task, self.sorting_task,
        })

    def test_manager_filter_never_expands_department_access(self):
        department = Department.objects.create(code="other", name="Other")
        self.task.department = department
        self.task.assignee = self.manager
        self.task.save()
        for value in ("0", "1"):
            response = self.get_list(self.manager, only_mine=value)
            self.assertNotIn(self.task, response.context["tasks"])

    def test_head_own_and_all_across_departments(self):
        role, _ = Role.objects.get_or_create(code="head", defaults={"name": "Head"})
        head = User.objects.create(login="only_mine_head", name="Head", role=role, department=self.department)
        self.assign_to(self.task, head)
        self.task.department = Department.objects.create(code="other", name="Other")
        self.task.save()
        response = self.get_list(head, only_mine="1")
        self.assertEqual(response.context["tasks"], [self.task])
        self.assertTrue(response.context["only_mine"])
        for params in ({}, {"only_mine": "0"}, {"only_mine": "invalid"}):
            with self.subTest(params=params):
                response = self.get_list(head, **params)
                self.assertFalse(response.context["only_mine"])
                self.assertTrue(response.context["show_only_mine_toggle"])
                self.assertEqual(set(response.context["tasks"]), {
                    self.task, self.second_task, self.sorting_task,
                })

    def test_employee_and_administrator_ignore_parameter_and_hide_toggle(self):
        for user, expected in (
            (self.user, {self.task, self.sorting_task}),
            (self.administrator, {self.task, self.second_task, self.sorting_task}),
        ):
            for value in ("0", "1"):
                response = self.get_list(user, only_mine=value)
                self.assertEqual(set(response.context["tasks"]), expected)
                self.assertFalse(response.context["show_only_mine_toggle"])
                self.assertNotContains(response, '<span class="quick-filter-text">Только свои</span>')

    def test_empty_own_list_explains_filter(self):
        response = self.get_list(self.manager)
        self.assertContains(response, "Выключите «Только свои»")
        self.assertEqual(response.context["tasks"], [])

    def test_search_and_final_status_filters_still_apply(self):
        self.assign_to(self.done_task, self.manager)
        self.assign_to(self.cancelled_task, self.manager)
        self.assertEqual(self.get_list(self.manager).context["tasks"], [])
        response = self.get_list(self.manager, show_done="1", show_cancelled="1", search="RND-3000")
        self.assertEqual(response.context["tasks"], [self.done_task])

    def test_pagination_preserves_filter_and_other_controls(self):
        for index in range(12):
            Task.objects.create(
                project_stream=self.project_stream, department=self.department,
                summary=f"Own {index}", assignee=self.manager,
                status=self.status, created_by=self.manager,
            )
        for value in ("0", "1"):
            response = self.get_list(self.manager, only_mine=value, search="Own",
                                     sort="created", direction="desc", week="2026-01-05", page="2")
            self.assertEqual(len(response.context["tasks"]), 2)
            query = response.context["pagination_query"]
            for part in (f"only_mine={value}", "search=Own", "sort=created", "direction=desc", "week=2026-01-05"):
                self.assertIn(part, query)

    def test_week_ajax_respects_own_filter(self):
        self.assign_to(self.task, self.manager)
        response = self.get_list(self.manager, format="json")
        self.assertEqual(set(response.json()["statuses"]), {str(self.task.pk)})
        response = self.get_list(self.manager, format="json", only_mine="0")
        self.assertEqual(set(response.json()["statuses"]), {
            str(task.pk) for task in (self.task, self.second_task, self.sorting_task)
        })
