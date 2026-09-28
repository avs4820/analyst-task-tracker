from django.contrib import admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.template.response import TemplateResponse

from .models import ProjectStream, Task, TaskArtifact, TaskStatus, TaskWeeklyStatus


class ArchiveFilter(admin.SimpleListFilter):
    title = "Архив"
    parameter_name = "archive"

    def lookups(self, request, model_admin):
        return (("active", "Активные"), ("archived", "Архивные"), ("all", "Все"))

    def choices(self, changelist):
        for value, title in self.lookup_choices:
            yield {
                "selected": (self.value() or "active") == value,
                "query_string": changelist.get_query_string({self.parameter_name: value}),
                "display": title,
            }

    def queryset(self, request, queryset):
        if self.value() == "all":
            return queryset
        return queryset.filter(archived_at__isnull=self.value() != "archived")


class ArchiveProtectedInline(admin.TabularInline):
    def has_add_permission(self, request, obj=None):
        return not (obj and obj.is_archived) and super().has_add_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.is_archived) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.is_archived) and super().has_delete_permission(request, obj)


class ArchivedWeeklyStatusInline(ArchiveProtectedInline):
    model = TaskWeeklyStatus
    extra = 0
    fields = ("week_start", "text", "updated_by", "created_at", "updated_at")
    readonly_fields = fields


@admin.register(ProjectStream)
class ProjectStreamAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "description")
    ordering = ("name",)


@admin.register(TaskStatus)
class TaskStatusAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "order",
        "is_final",
        "is_active",
    )
    list_filter = (
        "is_final",
        "is_active",
    )
    search_fields = (
        "name",
        "code",
    )
    ordering = (
        "order",
        "name",
    )


class TaskArtifactInline(ArchiveProtectedInline):
    model = TaskArtifact
    extra = 0
    fields = (
        "name",
        "url",
        "created_by",
    )


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    actions = ("archive_tasks", "restore_tasks")

    def get_queryset(self, request):
        queryset = Task.all_objects.all()
        # Autocomplete is used when assigning artifacts to an active task.
        if not request.user.is_superuser or request.path.endswith("/autocomplete/"):
            queryset = queryset.filter(archived_at__isnull=True)
        ordering = self.get_ordering(request)
        return queryset.order_by(*ordering) if ordering else queryset

    def has_archive_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.is_archived) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.is_archived) and super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        if queryset.filter(archived_at__isnull=False).exists():
            raise PermissionDenied
        super().delete_queryset(request, queryset)

    def get_inlines(self, request, obj):
        if obj and obj.is_archived:
            return (*self.inlines, ArchivedWeeklyStatusInline)
        return self.inlines

    @admin.action(description="Архивировать выбранные задачи", permissions=["archive"])
    def archive_tasks(self, request, queryset):
        return self._archive_action(request, queryset, restore=False)

    @admin.action(description="Восстановить выбранные задачи", permissions=["archive"])
    def restore_tasks(self, request, queryset):
        return self._archive_action(request, queryset, restore=True)

    def _archive_action(self, request, queryset, *, restore):
        if not self.has_archive_permission(request):
            raise PermissionDenied
        candidates = queryset.filter(archived_at__isnull=not restore)
        action = "restore_tasks" if restore else "archive_tasks"
        title = "Восстановить выбранные задачи" if restore else "Архивировать выбранные задачи"
        if request.POST.get("confirm_archive") == "yes":
            with transaction.atomic():
                # Resolve and lock the selection before changing any records.
                tasks = list(candidates.select_for_update())
                selected = Task.all_objects.filter(pk__in=[task.pk for task in tasks])
                count = selected.restore() if restore else selected.archive(request.user)
                for task in tasks:
                    self.log_change(request, task, "Восстановлено из архива" if restore else "Архивировано")
            self.message_user(request, f"{'Восстановлено' if restore else 'Архивировано'} задач: {count}.")
            return None
        return TemplateResponse(request, "admin/tracker/task/archive_confirmation.html", {
            **self.admin_site.each_context(request),
            "title": title,
            "opts": self.model._meta,
            "count": candidates.count(),
            "action": action,
            "selected_ids": request.POST.getlist(ACTION_CHECKBOX_NAME),
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
            "select_across": request.POST.get("select_across", "0"),
            "restore": restore,
        })

    list_display = (
        "display_name",
        "project_stream",
        "department",
        "assignee",
        "status",
        "created_by",
        "created_at",
        "updated_at",
        "archived_at",
        "archived_by",
    )
    list_filter = (
        ArchiveFilter,
        "project_stream",
        "department",
        "status",
        "assignee",
        "created_at",
    )
    search_fields = (
        "summary",
        "external_number",
        "assignee__login",
        "assignee__name",
    )
    autocomplete_fields = (
        "project_stream",
        "department",
        "status",
        "assignee",
        "created_by",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "archived_at",
        "archived_by",
    )
    ordering = ("-created_at",)
    inlines = (TaskArtifactInline,)

    @admin.display(description="Задача")
    def display_name(self, obj):
        return str(obj)


@admin.register(TaskArtifact)
class TaskArtifactAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if not request.user.is_superuser:
            queryset = queryset.filter(task__archived_at__isnull=True)
        return queryset

    def has_change_permission(self, request, obj=None):
        return not (obj and obj.task.is_archived) and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return not (obj and obj.task.is_archived) and super().has_delete_permission(request, obj)

    def delete_queryset(self, request, queryset):
        if queryset.filter(task__archived_at__isnull=False).exists():
            raise PermissionDenied
        super().delete_queryset(request, queryset)

    list_display = (
        "name",
        "task",
        "created_by",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "created_by",
        "created_at",
    )
    search_fields = (
        "name",
        "task__summary",
        "task__external_number",
        "url",
    )
    autocomplete_fields = (
        "task",
        "created_by",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
