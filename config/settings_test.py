"""Settings used by the automated test suite."""

from django.conf import global_settings

from . import settings as production_settings
from .settings import *  # noqa: F403


# Keep the production hashers available for focused integration tests while
# avoiding their intentionally expensive work factor in the rest of the suite.
PRODUCTION_PASSWORD_HASHERS = list(
    getattr(
        production_settings,
        "PASSWORD_HASHERS",
        global_settings.PASSWORD_HASHERS,
    )
)

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]
