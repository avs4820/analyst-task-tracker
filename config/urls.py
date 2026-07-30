"""
URL configuration for config project.
"""

from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path


def root_redirect(request):
    if request.user.is_authenticated:
        return redirect("tracker:task-list")

    return redirect("accounts:login")


urlpatterns = [
    path("", root_redirect, name="root"),
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("tracker/", include("tracker.urls")),
]