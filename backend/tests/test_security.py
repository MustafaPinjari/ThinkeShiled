# Feature: tender-shield
# Property-Based Tests: Security (Properties 19, 20)

from datetime import timedelta

import bleach
from django.test import override_settings
from hypothesis import given, settings as hyp_settings, HealthCheck
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase
from rest_framework.test import APIClient

from tenders.serializers import TenderSerializer

# ---------------------------------------------------------------------------
# Shared JWT settings for tests (HS256 — no RSA keys needed)
# ---------------------------------------------------------------------------

TEST_JWT = {
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

# All protected endpoints (method, path) — login is the only public one.
PROTECTED_ENDPOINTS = [
    ("GET",  "/api/v1/tenders/"),
    ("POST", "/api/v1/tenders/"),
    ("POST", "/api/v1/tenders/upload/"),
    ("GET",  "/api/v1/bids/"),
    ("POST", "/api/v1/bids/"),
    ("GET",  "/api/v1/companies/"),
    ("GET",  "/api/v1/graph/"),
    ("GET",  "/api/v1/alerts/"),
    ("GET",  "/api/v1/audit-log/"),
    ("POST", "/api/v1/auth/logout/"),
]

# Common XSS and SQL injection payloads
XSS_PAYLOADS = [
    '<script>alert("xss")</script>',
    '<img src=x onerror=alert(1)>',
    '"><script>alert(document.cookie)</script>',
    "javascript:alert(1)",
    '<svg onload=alert(1)>',
    '<iframe src="javascript:alert(1)">',
]

SQL_PAYLOADS = [
    "'; DROP TABLE tenders; --",
    "1 OR 1=1",
    "1; SELECT * FROM users",
    "' UNION SELECT null,null,null --",
    "admin'--",
]

ALL_INJECTION_PAYLOADS = XSS_PAYLOADS + SQL_PAYLOADS


# ===========================================================================
# PBT — Property 19: JWT Required for Protected Endpoints
# Validates: Requirements 12.1
# ===========================================================================

class PBTJWTProtectionTests(TestCase):
    """
    # Feature: tender-shield, Property 19: JWT Required for Protected Endpoints
    For any protected endpoint (all except /api/v1/auth/login/), a request
    without a valid JWT must receive HTTP 401.
    Validates: Requirements 12.1
    """

    @given(st.sampled_from(PROTECTED_ENDPOINTS))
    @hyp_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    @override_settings(SIMPLE_JWT=TEST_JWT, SECURE_SSL_REDIRECT=False)
    def test_property_19_jwt_required(self, endpoint):
        # Feature: tender-shield, Property 19: JWT Required for Protected Endpoints
        method, path = endpoint
        client = APIClient()
        fn = getattr(client, method.lower())
        resp = fn(path, format="json")
        self.assertEqual(
            resp.status_code,
            401,
            msg=f"Property 19 violated: {method} {path} returned {resp.status_code} without JWT",
        )


# ===========================================================================
# PBT — Property 20: Input Sanitization
# Validates: Requirements 12.4
# ===========================================================================

class PBTInputSanitizationTests(TestCase):
    """
    # Feature: tender-shield, Property 20: Input Sanitization
    For any user-supplied input containing SQL injection or XSS payloads,
    the stored value must be sanitized such that no injection is executed
    and no script content is stored verbatim.
    Validates: Requirements 12.4
    """

    def _valid_tender_data(self, **overrides):
        base = {
            "tender_id": "T-PBT-001",
            "title": "PBT Tender",
            "category": "IT",
            "estimated_value": "100000.00",
            "currency": "INR",
            "submission_deadline": "2026-12-31T23:59:59Z",
            "buyer_id": "B-001",
            "buyer_name": "Test Buyer",
        }
        base.update(overrides)
        return base

    @given(st.sampled_from(ALL_INJECTION_PAYLOADS))
    @hyp_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_property_20_injection_payloads_sanitized(self, payload):
        # Feature: tender-shield, Property 20: Input Sanitization
        data = self._valid_tender_data(
            title=payload,
            tender_id=f"T-{abs(hash(payload)) % 99999}",
        )
        s = TenderSerializer(data=data)
        if s.is_valid():
            stored = s.validated_data.get("title", "")
            self.assertNotIn("<script", stored.lower())
            self.assertNotIn("onerror", stored.lower())
            self.assertNotIn("onload", stored.lower())
            self.assertNotIn("<iframe", stored.lower())
            self.assertNotIn("<svg", stored.lower())

    @given(
        st.text(
            alphabet=st.characters(
                whitelist_categories=("Lu", "Ll", "Nd"),
                whitelist_characters=" -_",
            ),
            min_size=1,
            max_size=200,
        )
    )
    @hyp_settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_property_20_clean_input_passes_through(self, clean_text):
        # Feature: tender-shield, Property 20: Input Sanitization
        # Clean text (no HTML) must be accepted and stored unchanged by bleach
        sanitized = bleach.clean(clean_text, tags=[], attributes={}, strip=True)
        self.assertEqual(sanitized, clean_text)
