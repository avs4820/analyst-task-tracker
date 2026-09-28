from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tracker.models import Task, TaskArtifact, TaskWeeklyStatus


class Command(BaseCommand):
    help = (
        "Delete active tasks and their artifacts and weekly statuses. "
        "Archived tasks, their related data and reference data are preserved."
    )

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without changing the database.",
        )
        mode.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm deletion of active tasks only. Archives are preserved.",
        )
        parser.add_argument(
            "--expected-tasks",
            type=int,
            help=(
                "Abort unless the current task count matches this value. "
                "Recommended for production runs."
            ),
        )

    def handle(self, *args, **options):
        counts = {
            "tasks": Task.objects.count(),
            "artifacts": TaskArtifact.objects.filter(task__archived_at__isnull=True).count(),
            "weekly_statuses": TaskWeeklyStatus.objects.filter(task__archived_at__isnull=True).count(),
        }

        expected_tasks = options["expected_tasks"]
        if expected_tasks is not None and counts["tasks"] != expected_tasks:
            raise CommandError(
                "Task count changed: "
                f"expected {expected_tasks}, found {counts['tasks']}."
            )

        self.stdout.write(
            "Tasks: {tasks}; artifacts: {artifacts}; "
            "weekly statuses: {weekly_statuses}.".format(**counts)
        )

        if options["dry_run"]:
            self.stdout.write(self.style.WARNING("Dry run: nothing deleted."))
            return

        with transaction.atomic():
            Task.objects.all().delete()

        self.stdout.write(self.style.SUCCESS("Active tasks deleted. Archives preserved."))
