from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import identify_hasher
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Department, Role


User = get_user_model()
PRODUCTION_PASSWORD_HASHERS = getattr(
    settings,
    "PRODUCTION_PASSWORD_HASHERS",
    settings.PASSWORD_HASHERS,
)


@override_settings(PASSWORD_HASHERS=PRODUCTION_PASSWORD_HASHERS)
class ProductionPasswordHasherTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        department, _ = Department.objects.get_or_create(
            code="bsa",
            defaults={
                "name": "BSA",
                "is_active": True,
            },
        )
        role, _ = Role.objects.get_or_create(
            code=Role.Code.EMPLOYEE,
            defaults={
                "name": "Employee",
            },
        )

        cls.old_password = "ProductionPassword123!"
        cls.new_password = "ChangedProductionPassword456!"
        cls.user = User.objects.create_user(
            login="production-hasher-user",
            name="Production Hasher User",
            role=role,
            department=department,
            password=cls.old_password,
        )

    def test_password_uses_production_hasher(self):
        self.assertEqual(
            identify_hasher(self.user.password).algorithm,
            "pbkdf2_sha256",
        )
        self.assertTrue(self.user.check_password(self.old_password))

    def test_user_authenticates_with_production_hash(self):
        authenticated_user = authenticate(
            login=self.user.login,
            password=self.old_password,
        )

        self.assertEqual(authenticated_user, self.user)

    def test_changed_password_uses_production_hasher_and_authenticates(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": self.old_password,
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
        )

        self.assertRedirects(response, reverse("tracker:task-list"))

        self.user.refresh_from_db()
        self.assertEqual(
            identify_hasher(self.user.password).algorithm,
            "pbkdf2_sha256",
        )
        self.assertEqual(
            authenticate(
                login=self.user.login,
                password=self.new_password,
            ),
            self.user,
        )
