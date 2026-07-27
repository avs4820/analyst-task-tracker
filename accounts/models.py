from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class Role(models.Model):
    class Code(models.TextChoices):
        EMPLOYEE = "employee", "Employee"
        MANAGER = "manager", "Manager"
        ADMINISTRATOR = "administrator", "Administrator"

    code = models.CharField(
        max_length=32,
        choices=Code.choices,
        unique=True,
    )

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    class Meta:
        db_table = "roles"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class User(AbstractBaseUser, PermissionsMixin):
    name = models.CharField(
        max_length=255,
    )

    login = models.CharField(
        max_length=150,
        unique=True,
    )

    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="users",
    )

    is_active = models.BooleanField(
        default=True,
    )

    is_staff = models.BooleanField(
        default=False,
    )

    date_joined = models.DateTimeField(
        default=timezone.now,
    )

    objects = UserManager()

    USERNAME_FIELD = "login"
    REQUIRED_FIELDS = ["name", "role"]

    class Meta:
        db_table = "users"
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.login})"