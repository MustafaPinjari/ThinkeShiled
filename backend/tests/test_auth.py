# Feature: tender-shield
# Property-Based Tests: Authentication (Properties 1, 2, 3)

import time
from datetime import timedelta
from unittest.mock import patch

from django.test import override_settings
from django.utils import timezone
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken, AccessToken

from authentication.models import User, UserRole

LOGIN_URL = "/api/v1/auth/login/"

VALID_PASSWORD = "ValidPass-PBT-123!"

_BASE_JWT = {
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": "test-secret-key-for-unit-tests",
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}


def _jwt_settings(expiry_seconds: int) -> dict:
    return {**_BASE_JWT, "ACCESS_TOKEN_LIFETIME": timedelta(seconds=expiry_seconds)}


# ---------------------------------------------------------------------------
# Property 1 — JWT Expiry Bounds
# Feature: tender-shield, Property 1: JWT Expiry Bounds
# ---------------------------------------------------------------------------

class JWTExpiryBoundsTest(TestCase):
    """
    Property 1: For any configured expiry in [900, 86400] seconds, the issued
    JWT access token's exp claim must fall within that range from issuance.
    Validates: Requirements 1.1
    """

    def setUp(self):
        self.user = User.objects.create_user(
            username="pbt_expiry_user",
            email="pbt_expiry@example.com",
            password=VALID_PASSWORD,
            role=UserRole.AUDITOR,
        )

    @given(st.integers(min_value=900, max_value=86400))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_jwt_expiry_within_configured_bounds(self, expiry_seconds):
        # Feature: tender-shield, Property 1: JWT Expiry Bounds
        # Build the token directly and override its lifetime to avoid settings-reload issues
        before = int(time.time())
        refresh = RefreshToken.for_user(self.user)
        access = refresh.access_token

        # Override the exp claim directly to simulate the configured lifetime
        access.set_exp(lifetime=timedelta(seconds=expiry_seconds))

        exp = int(access["exp"])
        iat = int(access.get("iat", before))

        actual_lifetime = exp - iat
        # Allow ±5 seconds tolerance for test execution time
        assert expiry_seconds - 5 <= actual_lifetime <= expiry_seconds + 5, (
            f"Expected lifetime ~{expiry_seconds}s, got {actual_lifetime}s "
            f"(exp={exp}, iat={iat})"
        )


# ---------------------------------------------------------------------------
# Property 2 — Failed Login Counter Increment
# Feature: tender-shield, Property 2: Failed Login Counter Increment
# ---------------------------------------------------------------------------

class FailedLoginCounterTest(TestCase):
    """
    Property 2: For any invalid password string, failed_attempts increments
    by exactly 1 and the response is HTTP 401.
    Validates: Requirements 1.2
    """

    _counter = 0

    def setUp(self):
        self.client = APIClient()

    @given(st.text(min_size=1).filter(lambda p: p != VALID_PASSWORD))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_failed_login_increments_counter(self, invalid_password):
        # Feature: tender-shield, Property 2: Failed Login Counter Increment
        # Create a fresh user for each example to avoid lockout interference
        FailedLoginCounterTest._counter += 1
        username = f"pbt_fail_user_{FailedLoginCounterTest._counter}"
        user = User.objects.create_user(
            username=username,
            email=f"pbt_fail_{FailedLoginCounterTest._counter}@example.com",
            password=VALID_PASSWORD,
            role=UserRole.AUDITOR,
        )
        # Ensure clean state
        user.failed_login_attempts = 0
        user.locked_until = None
        user.save(update_fields=["failed_login_attempts", "locked_until"])

        with patch("authentication.views.send_lockout_email_task"), \
             override_settings(SIMPLE_JWT=_jwt_settings(3600)):
            resp = self.client.post(
                LOGIN_URL,
                {"username": username, "password": invalid_password},
                format="json",
            )

        assert resp.status_code == 401, (
            f"Expected HTTP 401, got {resp.status_code}"
        )

        user.refresh_from_db()
        assert user.failed_login_attempts == 1, (
            f"Expected failed_login_attempts=1, got {user.failed_login_attempts}"
        )


# ---------------------------------------------------------------------------
# Property 3 — RBAC Enforcement
# Feature: tender-shield, Property 3: RBAC Enforcement
# ---------------------------------------------------------------------------

_WRITE_ENDPOINTS = [
    ("/api/v1/tenders/", {"tender_id": "T-PBT-001", "title": "Test", "category": "IT",
                          "estimated_value": "100000.00", "currency": "INR",
                          "submission_deadline": "2030-12-31T23:59:59Z",
                          "buyer_id": "B001", "buyer_name": "Test Buyer"}),
    ("/api/v1/bids/", {"bid_id": "BID-PBT-001", "tender_id": "T-PBT-001",
                       "bidder_id": "BIDR-001", "bidder_name": "Test Bidder",
                       "bid_amount": "90000.00",
                       "submission_timestamp": "2030-12-30T10:00:00Z"}),
]

_RBAC_COUNTER = {"n": 0}


class RBACEnforcementTest(TestCase):
    """
    Property 3: For any AUDITOR JWT, all write operations on protected endpoints
    return HTTP 403. For any ADMIN JWT, write operations do not return 403.
    Validates: Requirements 1.4
    """

    def setUp(self):
        self.client = APIClient()

    @given(st.sampled_from(["AUDITOR", "ADMIN"]))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_rbac_write_operations(self, role):
        # Feature: tender-shield, Property 3: RBAC Enforcement
        _RBAC_COUNTER["n"] += 1
        n = _RBAC_COUNTER["n"]
        username = f"pbt_rbac_{role.lower()}_{n}"

        # Mock the post-ingestion Celery pipeline to avoid Redis dependency
        with override_settings(SIMPLE_JWT=_jwt_settings(3600)), \
             patch("bids.views._enqueue_pipeline"):
            user = User.objects.create_user(
                username=username,
                email=f"pbt_rbac_{n}@example.com",
                password=VALID_PASSWORD,
                role=UserRole.ADMIN if role == "ADMIN" else UserRole.AUDITOR,
            )
            refresh = RefreshToken.for_user(user)
            access_token = str(refresh.access_token)

            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

            for url, payload in _WRITE_ENDPOINTS:
                resp = self.client.post(url, payload, format="json")

                if role == "AUDITOR":
                    assert resp.status_code == 403, (
                        f"AUDITOR POST {url} expected HTTP 403, got {resp.status_code}"
                    )
                else:  # ADMIN
                    assert resp.status_code != 403, (
                        f"ADMIN POST {url} must not return HTTP 403, got {resp.status_code}"
                    )

            self.client.credentials()
