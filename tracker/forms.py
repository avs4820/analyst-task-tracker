from django import forms
from django.forms import inlineformset_factory

from .models import Task, TaskArtifact, TaskStatus, TaskWeeklyStatus


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = (
            "project_stream",
            "summary",
            "external_number",
            "external_url",
            "assignee",
            "status",
        )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if user and user.role.code == "employee":
            self.fields.pop("assignee")

    def save(self, commit=True):
        task = super().save(commit=False)

        if self.user and self.user.role.code == "employee":
            if task.pk:
                original_assignee_id = (
                    Task.objects.only("assignee_id")
                    .get(pk=task.pk)
                    .assignee_id
                )
                task.assignee_id = original_assignee_id
            else:
                task.assignee = self.user

        if commit:
            task.save()
            self.save_m2m()

        return task


class TaskPopupCreateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = (
            "project_stream",
            "summary",
            "external_number",
            "external_url",
            "assignee",
        )
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if user and user.role.code == "employee":
            self.fields.pop("assignee")

    def save(self, commit=True):
        task = super().save(commit=False)
        task.created_by = self.user
        task.status = TaskStatus.objects.get(code="new")

        if self.user.role.code == "employee":
            task.assignee = self.user

        if commit:
            task.save()

        return task


class TaskInlineEditForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if user and user.role.code == "employee":
            self.fields.pop("assignee")

    class Meta:
        model = Task
        fields = (
            "project_stream",
            "external_number",
            "external_url",
            "summary",
            "assignee",
        )
        widgets = {
            "project_stream": forms.Select(
                attrs={
                    "class": "task-edit-control",
                }
            ),
            "external_number": forms.TextInput(
                attrs={
                    "class": "task-edit-control",
                    "placeholder": "Например: RND-7010",
                }
            ),
            "external_url": forms.URLInput(
                attrs={
                    "class": "task-edit-control",
                    "placeholder": "https://...",
                }
            ),
            "summary": forms.Textarea(
                attrs={
                    "class": "task-edit-control task-summary-input",
                    "rows": 2,
                }
            ),
            "assignee": forms.Select(
                attrs={
                    "class": "task-edit-control",
                }
            ),
        }


class TaskStatusUpdateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ("status",)
        widgets = {
            "status": forms.Select(
                attrs={
                    "class": "task-status-select",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["status"].queryset = (
            self.fields["status"]
            .queryset
            .filter(is_active=True)
            .order_by("order", "name")
        )


class TaskArtifactForm(forms.ModelForm):
    class Meta:
        model = TaskArtifact
        fields = (
            "name",
            "url",
        )
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Например: Требования или прототип",
                }
            ),
            "url": forms.URLInput(
                attrs={
                    "placeholder": "https://example.com/document",
                }
            ),
        }


TaskArtifactFormSet = inlineformset_factory(
    parent_model=Task,
    model=TaskArtifact,
    form=TaskArtifactForm,
    fields=("name", "url"),
    extra=1,
    can_delete=True,
)


class TaskWeeklyStatusForm(forms.ModelForm):
    class Meta:
        model = TaskWeeklyStatus
        fields = ["text"]
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Опишите прогресс, результат и важные изменения за неделю",
                }
            ),
        }