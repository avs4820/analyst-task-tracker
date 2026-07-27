from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Role


User = get_user_model()


class AuthenticationViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role, _ = Role.objects.get_or_create(
            code=Role.Code.EMPLOYEE,
            defaults={
                "name": "Employee",
            },
        )

        cls.password = "StrongTestPassword123!"

        cls.user = User.objects.create_user(
            login="testuser",
            name="Test User",
            role=cls.role,
            password=cls.password,
        )

    def test_login_page_is_available(self):
        response = self.client.get(
            reverse("accounts:login")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "accounts/login.html",
        )

    def test_login_page_contains_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.get(
            reverse("accounts:login")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "csrfmiddlewaretoken")

    def test_user_can_login_with_correct_credentials(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "login": self.user.login,
                "password": self.password,
            },
        )

        self.assertRedirects(
            response,
            reverse("accounts:success"),
        )

        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            self.user.pk,
        )

    def test_user_cannot_login_with_wrong_password(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "login": self.user.login,
                "password": "wrong-password",
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Invalid login or password.",
        )

        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_user_cannot_login_with_unknown_login(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "login": "unknown-user",
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "Invalid login or password.",
        )

        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

        def test_anonymous_user_cannot_open_success_page(self):
            response = self.client.get(
                reverse("accounts:success")
            )

            self.assertRedirects(
                response,
                reverse("accounts:not_authorized"),
                fetch_redirect_response=False,
            )

    def test_authenticated_user_can_open_success_page(self):
        login_successful = self.client.login(
            login=self.user.login,
            password=self.password,
        )

        self.assertTrue(login_successful)

        response = self.client.get(
            reverse("accounts:success")
        )

        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(
            response,
            "accounts/success.html",
        )

        self.assertContains(
            response,
            self.user.login,
        )

    def test_not_authorized_page_returns_401(self):
        response = self.client.get(
            reverse("accounts:not_authorized")
        )

        self.assertEqual(response.status_code, 401)

        self.assertTemplateUsed(
            response,
            "accounts/not_authorized.html",
        )

    def test_authenticated_user_is_redirected_from_login_page(self):
        self.client.login(
            login=self.user.login,
            password=self.password,
        )

        response = self.client.get(
            reverse("accounts:login")
        )

        self.assertRedirects(
            response,
            reverse("accounts:success"),
        )

    def test_authenticated_user_is_redirected_from_not_authorized_page(self):
        self.client.login(
            login=self.user.login,
            password=self.password,
        )

        response = self.client.get(
            reverse("accounts:not_authorized")
        )

        self.assertRedirects(
            response,
            reverse("accounts:success"),
        )

    def test_logout_page_is_available_for_get_request(self):
        self.client.login(
            login=self.user.login,
            password=self.password,
        )

        response = self.client.get(
            reverse("accounts:logout")
        )

        self.assertEqual(response.status_code, 200)

        self.assertTemplateUsed(
            response,
            "accounts/logout.html",
        )

        self.assertIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_user_can_logout_with_post_request(self):
        self.client.login(
            login=self.user.login,
            password=self.password,
        )

        response = self.client.post(
            reverse("accounts:logout")
        )

        self.assertRedirects(
            response,
            reverse("accounts:login"),
        )

        self.assertNotIn(
            "_auth_user_id",
            self.client.session,
        )

    def test_logout_post_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)

        csrf_client.force_login(self.user)

        response = csrf_client.post(
            reverse("accounts:logout")
        )

        self.assertEqual(response.status_code, 403)

        self.assertIn(
            "_auth_user_id",
            csrf_client.session,
        )

    def test_login_post_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)

        response = csrf_client.post(
            reverse("accounts:login"),
            {
                "login": self.user.login,
                "password": self.password,
            },
        )

        self.assertEqual(response.status_code, 403)

        self.assertNotIn(
            "_auth_user_id",
            csrf_client.session,
        )