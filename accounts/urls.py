from django.urls import path

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
    path("logout/", views.logout_view, name="logout"),
]