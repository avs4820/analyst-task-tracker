from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied


def role_required(*allowed_roles):
    """
    Разрешает доступ только пользователям,
    роль которых входит в allowed_roles.

    Пример:
        @role_required("administrator")
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())

            if (
                not request.user.role
                or request.user.role.code not in allowed_roles
            ):
                raise PermissionDenied

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator