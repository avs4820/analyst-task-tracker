from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .decorators import role_required
from .forms import (
    TaskArtifactForm,
    TaskArtifactFormSet,
    TaskForm,
    TaskWeeklyStatusForm,
)
from .models import Task, TaskArtifact, TaskWeeklyStatus
from .utils import get_week_start


@login_required
def dashboard(request):
    return render(request, "tracker/dashboard.html")


@role_required("administrator")
def administration(request):
    return render(request, "tracker/administration.html")


@login_required
def task_list(request):
    current_week_start = get_week_start(timezone.localdate())
    latest_previous_week_start = current_week_start - timedelta(weeks=1)

    selected_week_value = request.GET.get("week")

    if selected_week_value:
        try:
            selected_date = date.fromisoformat(selected_week_value)
            previous_week_start = get_week_start(selected_date)
        except ValueError:
            previous_week_start = latest_previous_week_start
    else:
        previous_week_start = latest_previous_week_start

    if previous_week_start >= current_week_start:
        previous_week_start = latest_previous_week_start

    tasks = Task.objects.select_related(
        "project_stream",
        "status",
        "assignee",
        "created_by",
    )

    if request.user.role.code == "employee":
        tasks = tasks.filter(assignee=request.user)

    tasks = list(tasks)

    accessible_task_ids = [task.id for task in tasks]

    if request.method == "POST":
        task_id = request.POST.get("task_id")

        try:
            task_id = int(task_id)
        except (TypeError, ValueError):
            raise PermissionDenied

        if task_id not in accessible_task_ids:
            raise PermissionDenied

        task = get_object_or_404(Task, id=task_id)

        weekly_status = TaskWeeklyStatus.objects.filter(
            task=task,
            week_start=current_week_start,
        ).first()

        form = TaskWeeklyStatusForm(
            request.POST,
            instance=weekly_status,
            prefix=f"task-{task.id}",
        )

        if form.is_valid():
            weekly_status = form.save(commit=False)
            weekly_status.task = task
            weekly_status.week_start = current_week_start
            weekly_status.updated_by = request.user
            weekly_status.save()

            return redirect("tracker:task-list")
    else:
        task_id = None
        form = None

    weekly_statuses = TaskWeeklyStatus.objects.filter(
        task_id__in=accessible_task_ids,
        week_start__in=[
            current_week_start,
            previous_week_start,
        ],
    )

    current_statuses = {}
    previous_statuses = {}

    for weekly_status in weekly_statuses:
        if weekly_status.week_start == current_week_start:
            current_statuses[weekly_status.task_id] = weekly_status
        elif weekly_status.week_start == previous_week_start:
            previous_statuses[weekly_status.task_id] = weekly_status

    for task in tasks:
        current_status = current_statuses.get(task.id)

        task.current_weekly_status = current_status
        task.previous_weekly_status = previous_statuses.get(task.id)

        if (
            request.method == "POST"
            and task.id == task_id
            and form is not None
        ):
            task.weekly_status_form = form
        else:
            task.weekly_status_form = TaskWeeklyStatusForm(
                instance=current_status,
                prefix=f"task-{task.id}",
            )

    older_week_start = previous_week_start - timedelta(weeks=1)
    newer_week_start = previous_week_start + timedelta(weeks=1)

    can_move_forward = newer_week_start < current_week_start

    if request.GET.get("format") == "json":
        previous_status_data = {}

        for task in tasks:
            weekly_status = task.previous_weekly_status

            previous_status_data[str(task.id)] = {
                "text": weekly_status.text if weekly_status else "",
                "has_status": weekly_status is not None,
            }

        return JsonResponse(
            {
                "previous_week_start": previous_week_start.isoformat(),
                "previous_week_label": previous_week_start.strftime(
                    "%d.%m.%Y"
                ),
                "older_week_start": older_week_start.isoformat(),
                "newer_week_start": newer_week_start.isoformat(),
                "can_move_forward": can_move_forward,
                "statuses": previous_status_data,
            }
        )

    return render(
        request,
        "tracker/task_list.html",
        {
            "tasks": tasks,
            "current_week_start": current_week_start,
            "previous_week_start": previous_week_start,
            "older_week_start": older_week_start,
            "newer_week_start": newer_week_start,
            "can_move_forward": can_move_forward,
        },
    )

def check_task_access(user, task):
    if (
        user.role.code == "employee"
        and task.assignee_id != user.id
    ):
        raise PermissionDenied

@login_required
def task_create(request):
    task = Task(created_by=request.user)

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task)
        artifact_formset = TaskArtifactFormSet(
            request.POST,
            instance=task,
        )

        if form.is_valid() and artifact_formset.is_valid():
            with transaction.atomic():
                task = form.save()

                artifacts = artifact_formset.save(commit=False)

                for artifact in artifacts:
                    artifact.created_by = request.user
                    artifact.save()

            return redirect("tracker:task-list")
    else:
        form = TaskForm(instance=task)
        artifact_formset = TaskArtifactFormSet(instance=task)

    return render(
        request,
        "tracker/task_form.html",
        {
            "form": form,
            "artifact_formset": artifact_formset,
        },
    )


@login_required
def task_update(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    if (
        request.user.role.code == "employee"
        and task.assignee != request.user
    ):
        raise PermissionDenied

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task)
        artifact_formset = TaskArtifactFormSet(
            request.POST,
            instance=task,
        )

        if form.is_valid() and artifact_formset.is_valid():
            with transaction.atomic():
                form.save()

                artifacts = artifact_formset.save(commit=False)

                for deleted_artifact in artifact_formset.deleted_objects:
                    deleted_artifact.delete()

                for artifact in artifacts:
                    if not artifact.created_by_id:
                        artifact.created_by = request.user

                    artifact.save()

            return redirect("tracker:task-list")
    else:
        form = TaskForm(instance=task)
        artifact_formset = TaskArtifactFormSet(instance=task)

    return render(
        request,
        "tracker/task_form.html",
        {
            "form": form,
            "artifact_formset": artifact_formset,
            "task": task,
        },
    )


@login_required
@require_POST
def task_artifact_create(request, task_id):
    task = get_object_or_404(Task, id=task_id)

    check_task_access(request.user, task)

    form = TaskArtifactForm(request.POST)

    if not form.is_valid():
        return JsonResponse(
            {
                "success": False,
                "errors": form.errors.get_json_data(),
            },
            status=400,
        )

    artifact = form.save(commit=False)
    artifact.task = task
    artifact.created_by = request.user
    artifact.save()

    return JsonResponse(
        {
            "success": True,
            "artifact": {
                "id": artifact.id,
                "name": artifact.name,
                "url": artifact.url,
            },
        },
        status=201,
    )

@login_required
@require_POST
def task_artifact_delete(request, task_id, artifact_id):
    task = get_object_or_404(Task, id=task_id)

    check_task_access(request.user, task)

    artifact = get_object_or_404(
        TaskArtifact,
        id=artifact_id,
        task=task,
    )

    artifact.delete()

    return JsonResponse(
        {
            "success": True,
            "artifact_id": artifact_id,
        }
    )