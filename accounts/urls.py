from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("success/", views.success_view, name="success"),
    path(
        "not-authorized/",
        views.not_authorized_view,
        name="not_authorized",
    ),
    path(
        "password/change/",
        auth_views.PasswordChangeView.as_view(
            template_name="accounts/password_change.html",
            success_url=reverse_lazy("tracker:task-list"),
        ),
        name="password_change",
    ),
    path("logout/", views.logout_view, name="logout"),
]