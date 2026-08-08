from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserChangeForm, UserCreationForm
from .models import Department, Role, User


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "code",
        "is_active",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
        "code",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "name",
    )


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "name",
    )

    search_fields = (
        "code",
        "name",
    )

    ordering = (
        "name",
    )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm

    list_display = (
        "id",
        "login",
        "name",
        "role",
        "department",
        "is_active",
        "is_staff",
        "is_superuser",
    )

    list_filter = (
        "role",
        "department",
        "is_active",
        "is_staff",
        "is_superuser",
    )

    search_fields = (
        "login",
        "name",
    )

    ordering = (
        "name",
    )

    readonly_fields = (
        "last_login",
        "date_joined",
    )

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "login",
                    "password",
                )
            },
        ),
        (
            "Personal information",
            {
                "fields": (
                    "name",
                    "role",
                    "department",
                )
            },
        ),
        (
            "Access",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                )
            },
        ),
        (
            "Django permissions",
            {
                "fields": (
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                )
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "login",
                    "name",
                    "role",
                    "department",
                    "password1",
                    "password2",
                    "is_active",
                    "is_staff",
                ),
            },
        ),
    )

    filter_horizontal = (
        "groups",
        "user_permissions",
    )