from django.test import TestCase

from accounts.models import Department, Role, User
from tracker.forms import TaskForm, TaskInlineEditForm, TaskPopupCreateForm
from tracker.models import ProjectStream, Task, TaskStatus


class TaskProjectStreamFormTests(TestCase):
    create_forms = (TaskForm, TaskPopupCreateForm)
    edit_forms = (TaskForm, TaskInlineEditForm)

    @classmethod
    def setUpTestData(cls):
        department, _ = Department.objects.get_or_create(
            code="bsa", defaults={"name": "BSA"},
        )
        role, _ = Role.objects.get_or_create(
            code="employee", defaults={"name": "Employee"},
        )
        cls.user = User.objects.create(
            login="project_stream_employee", name="Employee",
            role=role, department=department,
        )
        cls.status, _ = TaskStatus.objects.get_or_create(
            code="new", defaults={"name": "Новая"},
        )
        cls.active = ProjectStream.objects.create(name="Active")
        cls.inactive = ProjectStream.objects.create(
            name="Inactive", is_active=False,
        )
        cls.other_inactive = ProjectStream.objects.create(
            name="Other inactive", is_active=False,
        )
        cls.task = Task.objects.create(
            project_stream=cls.inactive, summary="Original",
            department=department, assignee=cls.user,
            created_by=cls.user, status=cls.status,
        )

    def make_form(self, form_class, project, *, task=None):
        # Inline editing uses prefixed fields in both the UI and POST requests.
        prefix = "task-edit" if form_class is TaskInlineEditForm else None
        data = {
            "project_stream": project.pk,
            "summary": "Updated description",
            "status": self.status.pk,
        }
        if prefix:
            data = {f"{prefix}-{key}": value for key, value in data.items()}
        return form_class(
            data=data, user=self.user, prefix=prefix,
            instance=task or Task(created_by=self.user),
        )

    def test_creation_choices_only_include_active_projects(self):
        for form_class in self.create_forms:
            with self.subTest(form=form_class.__name__):
                form = form_class(user=self.user)
                choices = form.fields["project_stream"].queryset
                self.assertIn(self.active, choices)
                self.assertNotIn(self.inactive, choices)
                self.assertNotIn(self.other_inactive, choices)

    def test_creation_rejects_inactive_project_in_post(self):
        for form_class in self.create_forms:
            with self.subTest(form=form_class.__name__):
                form = self.make_form(form_class, self.inactive)
                self.assertFalse(form.is_valid())
                self.assertEqual(
                    form.errors.as_data()["project_stream"][0].code,
                    "invalid_choice",
                )

    def test_creation_with_active_project_saves(self):
        for form_class in self.create_forms:
            with self.subTest(form=form_class.__name__):
                form = self.make_form(form_class, self.active)
                self.assertTrue(form.is_valid(), form.errors)
                task = form.save()
                task.refresh_from_db()
                self.assertEqual(task.project_stream_id, self.active.pk)

    def test_edit_choices_include_only_active_and_current_project(self):
        for form_class in self.edit_forms:
            with self.subTest(form=form_class.__name__):
                form = form_class(user=self.user, instance=self.task)
                choices = form.fields["project_stream"].queryset
                self.assertIn(self.active, choices)
                self.assertIn(self.inactive, choices)
                self.assertNotIn(self.other_inactive, choices)

    def test_edit_can_keep_current_inactive_project(self):
        for form_class in self.edit_forms:
            with self.subTest(form=form_class.__name__):
                Task.objects.filter(pk=self.task.pk).update(summary="Original")
                task = Task.objects.get(pk=self.task.pk)
                form = self.make_form(form_class, self.inactive, task=task)
                self.assertTrue(form.is_valid(), form.errors)
                form.save()
                task.refresh_from_db()
                self.assertEqual(task.project_stream_id, self.inactive.pk)
                self.assertEqual(task.summary, "Updated description")

    def test_edit_rejects_other_inactive_project_in_post(self):
        for current in (self.active, self.inactive):
            for form_class in self.edit_forms:
                with self.subTest(current=current.name, form=form_class.__name__):
                    Task.objects.filter(pk=self.task.pk).update(project_stream=current)
                    task = Task.objects.get(pk=self.task.pk)
                    form = self.make_form(form_class, self.other_inactive, task=task)
                    self.assertFalse(form.is_valid())
                    self.assertEqual(
                        form.errors.as_data()["project_stream"][0].code,
                        "invalid_choice",
                    )
                    task.refresh_from_db()
                    self.assertEqual(task.project_stream_id, current.pk)

    def test_edit_can_switch_to_active_but_cannot_return_to_inactive(self):
        for form_class in self.edit_forms:
            with self.subTest(form=form_class.__name__):
                Task.objects.filter(pk=self.task.pk).update(project_stream=self.inactive)
                task = Task.objects.get(pk=self.task.pk)
                form = self.make_form(form_class, self.active, task=task)
                self.assertTrue(form.is_valid(), form.errors)
                form.save()
                task.refresh_from_db()
                self.assertEqual(task.project_stream_id, self.active.pk)
                form = self.make_form(form_class, self.inactive, task=task)
                self.assertFalse(form.is_valid())
                self.assertIn("project_stream", form.errors)

    def test_unsaved_task_cannot_keep_preassigned_inactive_project(self):
        for form_class in self.create_forms:
            with self.subTest(form=form_class.__name__):
                task = Task(project_stream=self.inactive, created_by=self.user)
                form = self.make_form(form_class, self.inactive, task=task)
                self.assertFalse(form.is_valid())
                self.assertIn("project_stream", form.errors)
