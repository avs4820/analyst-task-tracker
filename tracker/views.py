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
    TaskInlineEditForm,
    TaskPopupCreateForm,
    TaskStatusUpdateForm,
    TaskWeeklyStatusForm,
)
from .models import Task, TaskArtifact, TaskStatus, TaskWeeklyStatus
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
        "department",
    )

    if request.user.role.code == "employee":
        tasks = tasks.filter(assignee=request.user)

    elif request.user.role.code == "manager":
        if request.user.department_id:
            tasks = tasks.filter(
                department_id=request.user.department_id,
            )
        else:
            tasks = tasks.none()

    show_done = request.GET.get("show_done") == "1"
    show_cancelled = request.GET.get("show_cancelled") == "1"

    hidden_status_codes = []

    if not show_done:
        hidden_status_codes.append("done")

    if not show_cancelled:
        hidden_status_codes.append("cancelled")

    if hidden_status_codes:
        tasks = tasks.exclude(
            status__code__in=hidden_status_codes,
        )

    sort_fields = {
        "project": "project_stream__name",
        "number": "external_number",
        "summary": "summary",
    }

    sort_value = request.GET.get("sort", "project")
    sort_direction = request.GET.get("direction", "asc")

    if sort_value not in sort_fields:
        sort_value = "project"

    sort_field = sort_fields[sort_value]

    if sort_direction == "desc":
        sort_field = f"-{sort_field}"
    else:
        sort_direction = "asc"

    tasks = tasks.order_by(sort_field, "id")

    tasks = list(tasks)

    accessible_task_ids = [task.id for task in tasks]

    create_form = TaskPopupCreateForm(user=request.user)
    open_create_modal = False

    if request.method == "POST" and request.POST.get("action") == "create_task":
        create_form = TaskPopupCreateForm(
            request.POST,
            user=request.user,
        )
        open_create_modal = True

        if create_form.is_valid():
            create_form.save()
            return redirect(request.get_full_path())

        task_id = None
        form = None
    elif request.method == "POST":
        task_id = request.POST.get("task_id")

        try:
            task_id = int(task_id)
        except (TypeError, ValueError):
            raise PermissionDenied

        task = get_object_or_404(Task, id=task_id)
        check_task_access(request.user, task)

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

            return redirect(request.get_full_path())
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

        task.inline_edit_form = TaskInlineEditForm(
            instance=task,
            prefix=f"task-edit-{task.id}",
            user=request.user,
        )

        task.status_update_form = TaskStatusUpdateForm(
            instance=task,
            prefix=f"task-status-{task.id}",
        )

        task.status_update_form.fields["status"].widget.attrs[
            "data-status-code"
        ] = task.status.code

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
            "selected_sort": sort_value,
            "sort_direction": sort_direction,
            "show_done": show_done,
            "show_cancelled": show_cancelled,
            "create_form": create_form,
            "open_create_modal": open_create_modal,
        },
    )


def check_task_access(user, task):
    role_code = user.role.code

    if role_code == "employee":
        if task.assignee_id != user.id:
            raise PermissionDenied

    elif role_code == "manager":
        if (
            not user.department_id
            or task.department_id != user.department_id
        ):
            raise PermissionDenied

    elif role_code not in {"head", "administrator"}:
        raise PermissionDenied


@login_required
def task_create(request):
    task = Task(created_by=request.user)

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, user=request.user)
        artifact_formset = TaskArtifactFormSet(
            request.POST,
            instance=task,
        )

        if form.is_valid() and artifact_formset.is_valid():
            with transaction.atomic():
                task = form.save(commit=False)
                task.created_by = request.user
                task.status = get_object_or_404(TaskStatus, code="new")
                task.save()

                artifacts = artifact_formset.save(commit=False)

                for artifact in artifacts:
                    artifact.created_by = request.user
                    artifact.save()

            return redirect("tracker:task-list")
    else:
        form = TaskForm(instance=task, user=request.user)
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
    check_task_access(request.user, task)

    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, user=request.user)
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
        form = TaskForm(instance=task, user=request.user)
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
def task_inline_update(request, task_id):
    task = get_object_or_404(
        Task.objects.select_related(
            "project_stream",
            "assignee",
            "department",
        ),
        id=task_id,
    )

    check_task_access(request.user, task)

    form = TaskInlineEditForm(
        request.POST,
        instance=task,
        prefix=f"task-edit-{task.id}",
        user=request.user,
    )

    if not form.is_valid():
        return JsonResponse(
            {
                "success": False,
                "errors": form.errors.get_json_data(),
            },
            status=400,
        )

    task = form.save()

    return JsonResponse(
        {
            "success": True,
            "task": {
                "id": task.id,
                "project_stream": {
                    "id": task.project_stream_id,
                    "name": task.project_stream.name,
                },
                "external_number": task.external_number or "",
                "external_url": task.external_url or "",
                "summary": task.summary,
                "department": {
                    "id": task.department_id,
                    "code": task.department.code,
                    "name": task.department.name,
                },
                "assignee": {
                    "id": task.assignee_id,
                    "name": task.assignee.name,
                },
            },
        }
    )


@login_required
@require_POST
def task_status_update(request, task_id):
    task = get_object_or_404(
        Task.objects.select_related("status"),
        id=task_id,
    )

    check_task_access(request.user, task)

    form = TaskStatusUpdateForm(
        request.POST,
        instance=task,
        prefix=f"task-status-{task.id}",
    )

    if not form.is_valid():
        return JsonResponse(
            {
                "success": False,
                "errors": form.errors.get_json_data(),
            },
            status=400,
        )

    task = form.save()

    return JsonResponse(
        {
            "success": True,
            "status": {
                "id": task.status_id,
                "name": task.status.name,
                "code": task.status.code,
                "is_final": task.status.is_final,
            },
        }
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