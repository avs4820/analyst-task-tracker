from django.conf import settings
from django.db import models
from django.utils import timezone


class ProjectStream(models.Model):
    """
    Проект, стрим или функциональный домен,
    к которому относится задача.
    """

    name = models.CharField(
        max_length=150,
        unique=True,
        verbose_name="Проект / Стрим",
    )

    description = models.TextField(
        blank=True,
        verbose_name="Описание",
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
        verbose_name = "Проект / Стрим"
        verbose_name_plural = "Проекты / Стримы"
        ordering = ["name"]

    def __str__(self):
        return self.name


class TaskStatus(models.Model):
    """
    Справочник статусов задачи.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Название",
    )

    code = models.SlugField(
        max_length=50,
        unique=True,
        verbose_name="Код",
        help_text="Технический код статуса, например: in-progress",
    )

    order = models.PositiveIntegerField(
        default=0,
        verbose_name="Порядок отображения",
    )

    is_final = models.BooleanField(
        default=False,
        verbose_name="Финальный статус",
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
        verbose_name = "Статус задачи"
        verbose_name_plural = "Статусы задач"
        ordering = ["order", "name"]

    def __str__(self):
        return self.name


class TaskQuerySet(models.QuerySet):
    def archive(self, user):
        return self.filter(archived_at__isnull=True).update(
            archived_at=timezone.now(), archived_by=user,
        )

    def restore(self):
        return self.filter(archived_at__isnull=False).update(
            archived_at=None, archived_by=None,
        )


class ActiveTaskManager(models.Manager.from_queryset(TaskQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(archived_at__isnull=True)


class Task(models.Model):
    """
    Задача, которую ведёт аналитик.
    """

    objects = ActiveTaskManager()
    all_objects = TaskQuerySet.as_manager()

    archived_at = models.DateTimeField(
        null=True, blank=True, editable=False, db_index=True,
        verbose_name="Дата архивирования",
    )
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, editable=False,
        on_delete=models.PROTECT, related_name="archived_tasks",
        verbose_name="Архивировал",
    )

    @property
    def is_archived(self):
        return self.archived_at is not None

    project_stream = models.ForeignKey(
        ProjectStream,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="Проект / Стрим",
    )

    department = models.ForeignKey(
        "accounts.Department",
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="Отдел",
    )

    summary = models.CharField(
        max_length=500,
        verbose_name="Описание",
        help_text="Краткое описание того, что необходимо сделать",
    )

    external_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Номер",
        help_text="Например: RND-1234",
    )

    external_url = models.URLField(
        max_length=500,
        blank=True,
        verbose_name="Ссылка на внешнюю задачу",
        help_text="Например, ссылка на задачу в YouTrack",
    )

    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_tasks",
        verbose_name="Ответственный",
    )

    status = models.ForeignKey(
        TaskStatus,
        on_delete=models.PROTECT,
        related_name="tasks",
        verbose_name="Статус",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_tasks",
        verbose_name="Создал",
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
        verbose_name = "Задача"
        base_manager_name = "all_objects"
        default_manager_name = "objects"
        verbose_name_plural = "Задачи"
        ordering = ["-created_at"]

    def __str__(self):
        if self.external_number:
            return f"{self.external_number}: {self.summary}"

        return self.summary


class TaskArtifact(models.Model):
    """
    Внешний ресурс, связанный с задачей:
    документ, задача, страница Confluence и так далее.
    """

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="artifacts",
        verbose_name="Задача",
    )

    name = models.CharField(
        max_length=200,
        verbose_name="Название",
        help_text="Например: Требования, Прототип, API-документация",
    )

    url = models.URLField(
        max_length=1000,
        verbose_name="Ссылка",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_task_artifacts",
        verbose_name="Добавил",
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Дата добавления",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Дата изменения",
    )

    class Meta:
        verbose_name = "Артефакт задачи"
        verbose_name_plural = "Артефакты задач"
        ordering = ["created_at"]

    def __str__(self):
        return self.name

class TaskWeeklyStatus(models.Model):
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name="weekly_statuses",
        verbose_name="Задача",
    )
    week_start = models.DateField(
        verbose_name="Начало недели",
        help_text="Дата понедельника соответствующей недели",
    )
    text = models.TextField(
        blank=True,
        verbose_name="Еженедельный статус",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_weekly_statuses",
        verbose_name="Обновил",
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
        ordering = ["-week_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["task", "week_start"],
                name="unique_task_weekly_status",
            ),
        ]
        verbose_name = "Еженедельный статус задачи"
        verbose_name_plural = "Еженедельные статусы задач"

    def __str__(self):
        return f"{self.task} — неделя с {self.week_start}"
