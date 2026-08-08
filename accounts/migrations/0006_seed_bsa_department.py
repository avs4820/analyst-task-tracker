from django.db import migrations


def create_bsa_department_and_assign_users(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    User = apps.get_model("accounts", "User")

    bsa_department, _ = Department.objects.update_or_create(
        code="bsa",
        defaults={
            "name": "BSA",
            "is_active": True,
        },
    )

    User.objects.filter(
        department__isnull=True,
    ).update(
        department=bsa_department,
    )


def remove_bsa_department(apps, schema_editor):
    Department = apps.get_model("accounts", "Department")
    User = apps.get_model("accounts", "User")

    bsa_department = Department.objects.filter(
        code="bsa",
    ).first()

    if bsa_department is None:
        return

    User.objects.filter(
        department=bsa_department,
    ).update(
        department=None,
    )

    bsa_department.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_user_department"),
    ]

    operations = [
        migrations.RunPython(
            create_bsa_department_and_assign_users,
            remove_bsa_department,
        ),
    ]