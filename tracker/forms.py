from django import forms
from django.forms import inlineformset_factory
from django.db.models import Q

from accounts.models import User

from .models import Task, TaskArtifact, TaskStatus, TaskWeeklyStatus


def get_assignable_users(
    *,
    user,
    task=None,
    department=None,
):
    if not user or not user.is_authenticated:
        return User.objects.none()

    queryset = (
        User.objects
        .select_related("role", "department")
        .filter(is_active=True)
        .order_by("name", "login")
    )

    role_code = user.role.code
    existing_task = task if task and task.pk else None

    if department:
        target_department_id = department.pk
    elif existing_task:
        target_department_id = existing_task.department_id
    else:
        target_department_id = None

    if role_code == "employee":
        allowed_condition = Q(pk=user.pk)

    elif role_code == "manager":
        allowed_condition = Q(pk=user.pk)

        if user.department_id:
            allowed_condition |= Q(
                role__code="employee",
                department_id=user.department_id,
            )

    elif role_code == "head":
        # Head может быть исполнителем сам независимо
        # от отдела задачи.
        allowed_condition = Q(pk=user.pk)

        if target_department_id:
            allowed_condition |= Q(
                role__code__in=("manager", "employee"),
                department_id=target_department_id,
            )
        else:
            allowed_condition |= Q(
                role__code__in=("manager", "employee")
            )

    elif role_code == "administrator":
        # Administrator сам исполнителем быть не может.
        # Другие Head тоже не являются допустимыми исполнителями.
        if target_department_id:
            allowed_condition = Q(
                role__code__in=("manager", "employee"),
                department_id=target_department_id,
            )
        else:
            allowed_condition = Q(
                role__code__in=("manager", "employee")
            )

    else:
        return User.objects.none()

    # Исторический исполнитель существующей задачи остаётся
    # допустимым, пока отдел самой задачи не меняется.
    if (
        existing_task
        and target_department_id == existing_task.department_id
    ):
        allowed_condition |= Q(
            pk=existing_task.assignee_id
        )

    return queryset.filter(allowed_condition).distinct()


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
        elif user:
            self.fields["assignee"].queryset = get_assignable_users(
                user=user,
                task=self.instance,
            )

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

        if not task.pk and task.assignee_id:
            task.department = task.assignee.department

        if commit:
            task.save()
            self.save_m2m()

        return task


class AssigneeSelect(forms.Select):
    def create_option(
        self,
        name,
        value,
        label,
        selected,
        index,
        subindex=None,
        attrs=None,
    ):
        option = super().create_option(
            name,
            value,
            label,
            selected,
            index,
            subindex=subindex,
            attrs=attrs,
        )

        if value and getattr(value, "instance", None):
            option["attrs"]["data-department-id"] = (
                value.instance.department_id
            )

        return option


class TaskPopupCreateForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = (
            "project_stream",
            "summary",
            "external_number",
            "external_url",
            "department",
            "assignee",
        )
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "assignee": AssigneeSelect(),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        if not user:
            return

        role_code = user.role.code
        can_choose_department = role_code in (
            "head",
            "administrator",
        )

        selected_department = None

        if can_choose_department:
            self.fields["department"].queryset = (
                self.fields["department"]
                .queryset
                .filter(is_active=True)
                .order_by("name")
            )

            # Разрешаем оставить отдел пустым, если пользователь
            # сначала выбирает исполнителя. В clean() определим
            # отдел автоматически.
            self.fields["department"].required = False

            department_field_name = self.add_prefix("department")
            department_id = self.data.get(department_field_name)

            if department_id:
                selected_department = (
                    self.fields["department"]
                    .queryset
                    .filter(pk=department_id)
                    .first()
                )
        else:
            self.fields.pop("department")

        if role_code == "employee":
            self.fields.pop("assignee")

        else:
            self.fields["assignee"].queryset = get_assignable_users(
                user=user,
                department=selected_department,
            )

    def clean(self):
        cleaned_data = super().clean()

        if not self.user:
            return cleaned_data

        role_code = self.user.role.code
        assignee = cleaned_data.get("assignee")
        department = cleaned_data.get("department")

        if role_code in ("head", "administrator"):
            if assignee and not department:
                # Обычному Manager/Employee отдел можно определить
                # автоматически по исполнителю.
                if assignee.role.code in ("manager", "employee"):
                    department = assignee.department
                    cleaned_data["department"] = department

                # Если Head назначает самого себя, его технический
                # department использовать нельзя.
                elif (
                    role_code == "head"
                    and assignee.pk == self.user.pk
                ):
                    self.add_error(
                        "department",
                        "Выберите отдел задачи.",
                    )

            if department and assignee:
                head_assigns_self = (
                    role_code == "head"
                    and assignee.pk == self.user.pk
                )

                if (
                    not head_assigns_self
                    and assignee.department_id != department.id
                ):
                    self.add_error(
                        "assignee",
                        "Исполнитель должен относиться к выбранному отделу.",
                    )

        return cleaned_data

    def save(self, commit=True):
        task = super().save(commit=False)
        task.created_by = self.user
        task.status = TaskStatus.objects.get(code="new")

        role_code = self.user.role.code

        if role_code == "employee":
            task.assignee = self.user
            task.department = self.user.department

        elif role_code == "manager":
            task.department = self.user.department

        elif task.department_id is None and task.assignee_id:
            task.department = task.assignee.department

        if commit:
            task.save()

        return task


class TaskInlineEditForm(forms.ModelForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        can_change_department = (
            user
            and user.role.code in ("head", "administrator")
        )

        selected_department = None

        if can_change_department:
            self.fields["department"].queryset = (
                self.fields["department"]
                .queryset
                .filter(is_active=True)
                .order_by("name")
            )

            department_field_name = self.add_prefix("department")
            department_id = self.data.get(department_field_name)

            if department_id:
                selected_department = (
                    self.fields["department"]
                    .queryset
                    .filter(pk=department_id)
                    .first()
                )
        else:
            self.fields.pop("department")

        if user and user.role.code == "employee":
            self.fields.pop("assignee")
        elif user:
            if can_change_department and not self.is_bound:
                assignee_queryset = get_assignable_users(
                    user=user,
                )

                if self.instance.pk:
                    assignee_queryset = User.objects.filter(
                        Q(
                            pk__in=assignee_queryset.values("pk")
                        )
                        | Q(
                            pk=self.instance.assignee_id,
                            is_active=True,
                        )
                    )

                self.fields["assignee"].queryset = (
                    assignee_queryset
                    .select_related("role", "department")
                    .distinct()
                    .order_by("name", "login")
                )
            else:
                self.fields["assignee"].queryset = get_assignable_users(
                    user=user,
                    task=self.instance,
                    department=selected_department,
                )

    def clean(self):
        cleaned_data = super().clean()

        department = cleaned_data.get("department")
        assignee = cleaned_data.get("assignee")

        if department and assignee:
            head_assigns_self = (
                self.user
                and self.user.role.code == "head"
                and assignee.pk == self.user.pk
            )

            if (
                not head_assigns_self
                and assignee.department_id != department.id
            ):
                self.add_error(
                    "assignee",
                    "Исполнитель должен относиться к выбранному отделу.",
                )

        return cleaned_data


    class Meta:
        model = Task
        fields = (
            "project_stream",
            "external_number",
            "external_url",
            "department",
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
            "department": forms.Select(
                attrs={
                    "class": "task-edit-control",
                }
            ),
            "summary": forms.Textarea(
                attrs={
                    "class": "task-edit-control task-summary-input",
                    "rows": 2,
                }
            ),
            "assignee": AssigneeSelect(
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