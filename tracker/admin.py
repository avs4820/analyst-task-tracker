from django.contrib import admin

from .models import ProjectStream, Task, TaskArtifact, TaskStatus


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


class TaskArtifactInline(admin.TabularInline):
    model = TaskArtifact
    extra = 0
    fields = (
        "name",
        "url",
        "created_by",
    )


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "project_stream",
        "assignee",
        "status",
        "created_by",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "project_stream",
        "status",
        "assignee",
        "created_at",
    )
    search_fields = (
        "summary",
        "external_number",
        "assignee__username",
        "assignee__email",
    )
    autocomplete_fields = (
        "project_stream",
        "status",
        "assignee",
        "created_by",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
    inlines = (TaskArtifactInline,)

    @admin.display(description="Задача")
    def display_name(self, obj):
        return str(obj)


@admin.register(TaskArtifact)
class TaskArtifactAdmin(admin.ModelAdmin):
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