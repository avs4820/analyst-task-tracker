from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import Department, Role


User = get_user_model()


class AuthenticationViewsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department, _ = Department.objects.get_or_create(
            code="bsa",
            defaults={
                "name": "BSA",
                "is_active": True,
            },
        )

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
            department=cls.department,
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
        self.assertContains(
            response,
            "csrfmiddlewaretoken",
        )

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
            reverse("tracker:task-list"),
        )

        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            self.user.pk,
        )

    def test_login_redirects_to_next_page_when_next_is_valid(self):
        task_list_url = reverse("tracker:task-list")

        response = self.client.post(
            reverse("accounts:login"),
            {
                "login": self.user.login,
                "password": self.password,
                "next": task_list_url,
            },
        )

        self.assertRedirects(
            response,
            task_list_url,
        )

    def test_login_ignores_external_next_url(self):
        response = self.client.post(
            reverse("accounts:login"),
            {
                "login": self.user.login,
                "password": self.password,
                "next": "https://malicious.example.com/",
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
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

    def test_anonymous_user_is_redirected_from_success_page(self):
        response = self.client.get(
            reverse("accounts:success")
        )

        self.assertRedirects(
            response,
            reverse("accounts:not_authorized"),
            fetch_redirect_response=False,
        )

    def test_authenticated_user_is_redirected_from_success_page_to_task_list(
        self,
    ):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("accounts:success")
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
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
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("accounts:login")
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

    def test_authenticated_user_is_redirected_from_not_authorized_page(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("accounts:not_authorized")
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

    def test_logout_page_is_available_for_get_request(self):
        self.client.force_login(self.user)

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
        self.client.force_login(self.user)

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


class ThemePreferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department, _ = Department.objects.get_or_create(
            code="bsa",
            defaults={
                "name": "BSA",
                "is_active": True,
            },
        )
        cls.role, _ = Role.objects.get_or_create(
            code=Role.Code.EMPLOYEE,
            defaults={"name": "Employee"},
        )
        cls.user = User.objects.create_user(
            login="theme-user",
            name="Theme User",
            role=cls.role,
            department=cls.department,
            password="StrongThemePassword123!",
        )

    def test_default_theme_is_light(self):
        response = self.client.get(reverse("accounts:login"))

        self.assertContains(response, 'data-theme="light"')

    def test_authenticated_user_can_select_dark_theme(self):
        self.client.force_login(self.user)
        task_list_url = reverse("tracker:task-list")

        response = self.client.post(
            reverse("accounts:set_theme"),
            {
                "theme": "dark",
                "next": task_list_url,
            },
        )

        self.assertRedirects(response, task_list_url)
        self.assertEqual(self.client.session["ui_theme"], "dark")

        page_response = self.client.get(task_list_url)
        self.assertContains(page_response, 'data-theme="dark"')
        self.assertContains(page_response, "Светлая тема")
        self.assertContains(page_response, "tracker/theme.css")

    def test_user_can_switch_back_to_light_theme(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["ui_theme"] = "dark"
        session.save()

        response = self.client.post(
            reverse("accounts:set_theme"),
            {"theme": "light"},
        )

        self.assertRedirects(response, reverse("tracker:task-list"))
        self.assertEqual(self.client.session["ui_theme"], "light")

    def test_invalid_theme_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:set_theme"),
            {"theme": "sepia"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("ui_theme", self.client.session)

    def test_external_next_url_is_ignored(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:set_theme"),
            {
                "theme": "dark",
                "next": "https://malicious.example.com/",
            },
        )

        self.assertRedirects(response, reverse("tracker:task-list"))

    def test_anonymous_user_cannot_change_theme(self):
        response = self.client.post(
            reverse("accounts:set_theme"),
            {"theme": "dark"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertNotIn("ui_theme", self.client.session)

    def test_set_theme_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(
            reverse("accounts:set_theme"),
            {"theme": "dark"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn("ui_theme", csrf_client.session)


class PasswordChangeViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.department, _ = Department.objects.get_or_create(
            code="bsa",
            defaults={
                "name": "BSA",
                "is_active": True,
            },
        )

        cls.role, _ = Role.objects.get_or_create(
            code=Role.Code.EMPLOYEE,
            defaults={
                "name": "Employee",
            },
        )

        cls.old_password = "StrongOldPassword123!"
        cls.new_password = "StrongNewPassword456!"

        cls.user = User.objects.create_user(
            login="password-user",
            name="Password User",
            role=cls.role,
            department=cls.department,
            password=cls.old_password,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(
            reverse("accounts:password_change")
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("accounts:login"),
            response.url,
        )

    def test_password_change_page_is_available(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("accounts:password_change")
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "accounts/password_change.html",
        )
        self.assertContains(response, "Текущий пароль")
        self.assertContains(response, "Новый пароль")
        self.assertContains(response, "Подтверждение нового пароля")

    def test_password_change_page_contains_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.get(
            reverse("accounts:password_change")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "csrfmiddlewaretoken",
        )

    def test_user_can_change_password(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": self.old_password,
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
        )

        self.assertRedirects(
            response,
            reverse("tracker:task-list"),
        )

        self.user.refresh_from_db()
        self.assertTrue(
            self.user.check_password(self.new_password)
        )
        self.assertFalse(
            self.user.check_password(self.old_password)
        )

    def test_user_remains_authenticated_after_password_change(self):
        self.client.force_login(self.user)

        self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": self.old_password,
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
        )

        self.assertEqual(
            int(self.client.session["_auth_user_id"]),
            self.user.pk,
        )

    def test_wrong_current_password_is_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": "WrongCurrentPassword123!",
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "old_password",
            "Your old password was entered incorrectly. Please enter it again.",
        )

        self.user.refresh_from_db()
        self.assertTrue(
            self.user.check_password(self.old_password)
        )

    def test_different_new_passwords_are_rejected(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("accounts:password_change"),
            {
                "old_password": self.old_password,
                "new_password1": self.new_password,
                "new_password2": "DifferentNewPassword789!",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response.context["form"],
            "new_password2",
            "The two password fields didn’t match.",
        )

        self.user.refresh_from_db()
        self.assertTrue(
            self.user.check_password(self.old_password)
        )

    def test_password_change_post_requires_csrf_token(self):
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)

        response = csrf_client.post(
            reverse("accounts:password_change"),
            {
                "old_password": self.old_password,
                "new_password1": self.new_password,
                "new_password2": self.new_password,
            },
        )

        self.assertEqual(response.status_code, 403)

        self.user.refresh_from_db()
        self.assertTrue(
            self.user.check_password(self.old_password)
        )
