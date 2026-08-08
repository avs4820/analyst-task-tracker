from typing import Any

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Manager for the custom User model."""

    use_in_migrations = True

    def create_user(
        self,
        login: str,
        name: str,
        role: Any,
        department: Any,
        password: str | None = None,
        **extra_fields: Any,
    ):
        if not login:
            raise ValueError("Login must be provided.")

        if not name:
            raise ValueError("Name must be provided.")

        if role is None:
            raise ValueError("Role must be provided.")

        if department is None:
            raise ValueError("Department must be provided.")

        login = login.strip().lower()
        name = name.strip()

        user = self.model(
            login=login,
            name=name,
            role=role,
            department=department,
            **extra_fields,
        )

        user.set_password(password)
        user.save(using=self._db)

        return user

    def create_superuser(
        self,
        login: str,
        name: str,
        role: Any,
        department: Any,
        password: str | None = None,
        **extra_fields: Any,
    ):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")

        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(
            login=login,
            name=name,
            role=role,
            department=department,
            password=password,
            **extra_fields,
        )