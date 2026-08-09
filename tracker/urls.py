from django.urls import path

from .views import (
    administration,
    dashboard,
    task_artifact_create,
    task_artifact_delete,
    task_create,
    task_inline_update,
    task_list,
    task_status_update,
    task_update,
    status_summary,
)


app_name = "tracker"


urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("administration/", administration, name="administration"),
    path("tasks/", task_list, name="task-list"),
    path(
        "tasks/status-summary/",
        status_summary,
        name="status-summary",
    ),
    path("tasks/create/", task_create, name="task-create"),
    path("tasks/<int:task_id>/edit/", task_update, name="task-update"),
    path(
        "tasks/<int:task_id>/inline-update/",
        task_inline_update,
        name="task-inline-update",
    ),
    path(
        "tasks/<int:task_id>/status-update/",
        task_status_update,
        name="task-status-update",
    ),
    path(
        "tasks/<int:task_id>/artifacts/create/",
        task_artifact_create,
        name="task-artifact-create",
    ),
    path(
        "tasks/<int:task_id>/artifacts/<int:artifact_id>/delete/",
        task_artifact_delete,
        name="task-artifact-delete",
    ),
]
