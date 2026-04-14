from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.models import User, UserRole

TEST_JWT_SETTINGS = {
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=3600),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": "test-secret-key-for-unit-tests",
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
}

LOGIN_URL = "/api/v1/auth/login/"
LOGOUT_URL = "/api/v1/auth/logout/"
REFRESH_URL = "/api/v1/auth/refresh/"


@override_settings(SIMPLE_JWT=TEST_JWT_SETTINGS)
class LoginViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="correct-password-123",
            role=UserRole.AUDITOR,
        )

    @patch("authentication.views.send_lockout_email_task")
    def test_login_success(self, mock_task):
        resp = self.client.post(
            LOGIN_URL,
            {"username": "testuser", "password": "correct-password-123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertIn("role", resp.data)
        self.assertEqual(resp.data["role"], UserRole.AUDITOR)

    @patch("authentication.views.send_lockout_email_task")
    def test_login_failure_increments_counter(self, mock_task):
        resp = self.client.post(
            LOGIN_URL,
            {"username": "testuser", "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 1)

    @patch("authentication.views.send_lockout_email_task")
    def test_login_failure_returns_failed_attempts(self, mock_task):
        resp = self.client.post(
            LOGIN_URL,
            {"username": "testuser", "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("failed_attempts", resp.data)
        self.assertEqual(resp.data["failed_attempts"], 1)

    @patch("authentication.views.send_lockout_email_task")
    def test_account_lockout_after_5_failures(self, mock_task):
        for _ in range(5):
            self.client.post(
                LOGIN_URL,
                {"username": "testuser", "password": "wrong-password"},
                format="json",
            )

        # 6th attempt should return locked
        resp = self.client.post(
            LOGIN_URL,
            {"username": "testuser", "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Account locked", resp.data.get("detail", ""))
        mock_task.delay.assert_called_once_with(self.user.id)

    @patch("authentication.views.send_lockout_email_task")
    def test_locked_account_cannot_login(self, mock_task):
        self.user.locked_until = timezone.now() + timedelta(minutes=10)
        self.user.save(update_fields=["locked_until"])

        resp = self.client.post(
            LOGIN_URL,
            {"username": "testuser", "password": "correct-password-123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
        self.assertIn("Account locked", resp.data.get("detail", ""))

    @patch("authentication.views.send_lockout_email_task")
    def test_login_resets_counter_on_success(self, mock_task):
        self.user.failed_login_attempts = 3
        self.user.save(update_fields=["failed_login_attempts"])

        self.client.post(
            LOGIN_URL,
            {"username": "testuser", "password": "correct-password-123"},
            format="json",
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.failed_login_attempts, 0)


@override_settings(SIMPLE_JWT=TEST_JWT_SETTINGS)
class TokenRefreshTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="refreshuser",
            email="refresh@example.com",
            password="password-123",
        )

    def test_token_refresh(self):
        refresh = RefreshToken.for_user(self.user)
        resp = self.client.post(
            REFRESH_URL,
            {"refresh": str(refresh)},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)


@override_settings(SIMPLE_JWT=TEST_JWT_SETTINGS)
class LogoutViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="logoutuser",
            email="logout@example.com",
            password="password-123",
        )

    def test_logout_blacklists_token(self):
        refresh = RefreshToken.for_user(self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")

        resp = self.client.post(
            LOGOUT_URL,
            {"refresh": str(refresh)},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["detail"], "Logged out successfully.")

        # Subsequent refresh with same token should fail
        self.client.credentials()
        resp2 = self.client.post(
            REFRESH_URL,
            {"refresh": str(refresh)},
            format="json",
        )
        self.assertEqual(resp2.status_code, 401)

    def test_logout_requires_authentication(self):
        resp = self.client.post(LOGOUT_URL, {"refresh": "sometoken"}, format="json")
        self.assertEqual(resp.status_code, 401)


@override_settings(SIMPLE_JWT=TEST_JWT_SETTINGS)
class ProtectedEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="protecteduser",
            email="protected@example.com",
            password="password-123",
        )

    def test_protected_endpoint_requires_jwt(self):
        # Logout endpoint requires auth — test without token
        resp = self.client.post(LOGOUT_URL, {"refresh": "token"}, format="json")
        self.assertEqual(resp.status_code, 401)
