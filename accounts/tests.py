from django.contrib.auth import authenticate, get_user_model
from django.test import TestCase

from .models import Role


User = get_user_model()


class UserModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee_role = Role.objects.create(
            code=Role.Code.EMPLOYEE,
            name="Employee",
        )

    def test_create_user(self):
        user = User.objects.create_user(
            login="test.user",
            name="Test User",
            role=self.employee_role,
            password="StrongTestPassword123",
        )

        self.assertEqual(user.login, "test.user")
        self.assertEqual(user.name, "Test User")
        self.assertEqual(user.role, self.employee_role)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_staff)
        self.assertTrue(
            user.check_password("StrongTestPassword123")
        )

    def test_login_is_normalized(self):
        user = User.objects.create_user(
            login="TEST.USER",
            name="Test User",
            role=self.employee_role,
            password="StrongTestPassword123",
        )

        self.assertEqual(user.login, "test.user")

    def test_password_is_hashed(self):
        user = User.objects.create_user(
            login="test.user",
            name="Test User",
            role=self.employee_role,
            password="StrongTestPassword123",
        )

        self.assertNotEqual(
            user.password,
            "StrongTestPassword123",
        )

    def test_authentication(self):
        User.objects.create_user(
            login="test.user",
            name="Test User",
            role=self.employee_role,
            password="StrongTestPassword123",
        )

        authenticated_user = authenticate(
            login="test.user",
            password="StrongTestPassword123",
        )

        self.assertIsNotNone(authenticated_user)
        self.assertEqual(
            authenticated_user.login,
            "test.user",
        )

    def test_create_user_without_role_fails(self):
        with self.assertRaises(ValueError):
            User.objects.create_user(
                login="test.user",
                name="Test User",
                role=None,
                password="StrongTestPassword123",
            )