from django.db import migrations


def create_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")

    roles = (
        {
            "code": "employee",
            "name": "Employee",
        },
        {
            "code": "manager",
            "name": "Manager",
        },
        {
            "code": "administrator",
            "name": "Administrator",
        },
    )

    for role_data in roles:
        Role.objects.update_or_create(
            code=role_data["code"],
            defaults={
                "name": role_data["name"],
            },
        )


def remove_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")

    Role.objects.filter(
        code__in=(
            "employee",
            "manager",
            "administrator",
        )
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            create_roles,
            remove_roles,
        ),
    ]