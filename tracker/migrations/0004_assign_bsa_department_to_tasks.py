from django.db import migrations


def assign_bsa_department_to_tasks(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    Task = apps.get_model("tracker", "Task")

    bsa_department = Department.objects.get(
        code="bsa",
    )

    Task.objects.filter(
        department__isnull=True,
    ).update(
        department=bsa_department,
    )


def clear_bsa_department_from_tasks(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    Task = apps.get_model("tracker", "Task")

    bsa_department = Department.objects.filter(
        code="bsa",
    ).first()

    if bsa_department is None:
        return

    Task.objects.filter(
        department=bsa_department,
    ).update(
        department=None,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0006_seed_bsa_department"),
        ("tracker", "0003_task_department"),
    ]

    operations = [
        migrations.RunPython(
            assign_bsa_department_to_tasks,
            clear_bsa_department_from_tasks,
        ),
    ]