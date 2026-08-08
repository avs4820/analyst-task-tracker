from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .managers import UserManager


class Department(models.Model):
    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Название",
    )

    code = models.SlugField(
        max_length=50,
        unique=True,
        verbose_name="Код",
        help_text="Технический код отдела, например: bsa",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="Активен",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата создания",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата изменения",
    )

    class Meta:
        db_table = "departments"
        verbose_name = "Отдел"
        verbose_name_plural = "Отделы"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Role(models.Model):
    class Code(models.TextChoices):
        EMPLOYEE = "employee", "Employee"
        MANAGER = "manager", "Manager"
        HEAD = "head", "Head"
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

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="users",
        verbose_name="Отдел",
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