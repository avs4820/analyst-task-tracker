from django import forms
from django.forms import inlineformset_factory

from .models import Task, TaskArtifact, TaskWeeklyStatus


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