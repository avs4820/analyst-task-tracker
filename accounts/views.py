from django.contrib.auth import authenticate, login, logout
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .forms import LoginForm


@require_http_methods(["GET", "POST"])
def login_view(request):
    # Если пользователь уже авторизован,
    # повторно показывать страницу входа не нужно.
    if request.user.is_authenticated:
        return redirect("tracker:task-list")

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        login_value = form.cleaned_data["login"]
        password = form.cleaned_data["password"]

        user = authenticate(
            request,
            login=login_value,
            password=password,
        )

        if user is not None:
            login(request, user)

            next_url = (
                request.POST.get("next")
                or request.GET.get("next")
            )

            # Проверяем адрес перенаправления,
            # чтобы нельзя было отправить пользователя
            # на сторонний сайт.
            if next_url and url_has_allowed_host_and_scheme(
                url=next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect("tracker:task-list")

        form.add_error(
            None,
            "Invalid login or password.",
        )

    return render(
        request,
        "accounts/login.html",
        {
            "form": form,
            "next": request.GET.get("next", ""),
        },
    )


def success_view(request):
    if not request.user.is_authenticated:
        return redirect("accounts:not_authorized")

    return redirect("tracker:task-list")


def not_authorized_view(request):
    if request.user.is_authenticated:
        return redirect("tracker:task-list")

    return render(
        request,
        "accounts/not_authorized.html",
        status=401,
    )


@require_http_methods(["GET", "POST"])
def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect("accounts:login")

    return render(
        request,
        "accounts/logout.html",
    )