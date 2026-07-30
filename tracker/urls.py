from django.urls import path

from .views import (
    administration,
    dashboard,
    task_artifact_create,
    task_artifact_delete,
    task_create,
    task_list,
    task_update,
)


app_name = "tracker"


urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("administration/", administration, name="administration"),
    path("tasks/", task_list, name="task-list"),
    path("tasks/create/", task_create, name="task-create"),
    path("tasks/<int:task_id>/edit/", task_update, name="task-update"),
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