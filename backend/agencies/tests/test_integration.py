"""
Integration tests for the agency registration → email verification → login flow.

Tests the full end-to-end flow using Django's test client against the real API
endpoints. Celery tasks are mocked with unittest.mock.patch so emails are not
actually sent.

Requirements: 1.4–1.9, 2.1–2.3, 9.1–9.3
"""

import hashlib
import json
import os
import uuid
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from agencies.models import Agency, AgencyStatus, EmailVerificationToken
from audit.models import AuditLog, EventType
from authentication.models import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_gstin() -> str:
    """
    Generate a unique, format-valid GSTIN for each test to avoid DB uniqueness
    collisions. Pattern: [0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}
    Uses 27AAPFU<4 digits>A1Z5 — the 4-digit section varies per test.
    """
    suffix = uuid.uuid4().hex[:4]
    digits = "".join(str(int(c, 16) % 10) for c in suffix)
    return f"27AAPFU{digits}A1Z5"


def _valid_payload(**overrides) -> dict:
    """Return a complete, valid registration payload."""
    uid = uuid.uuid4().hex[:8]
    payload = {
        "legal_name": f"Test Agency {uid}",
        "gstin": _unique_gstin(),
        "ministry": "Ministry of Finance",
        "contact_name": "Test Contact",
        "contact_email": f"admin-{uid}@example.com",
        "password": "SecurePass123!",
    }
    payload.update(overrides)
    return payload


REGISTER_URL = "/api/v1/agencies/register/"
VERIFY_URL = "/api/v1/agencies/verify-email/"
LOGIN_URL = "/api/v1/agencies/login/"

# Fixed 32-byte value used when patching os.urandom so we can predict token_hex
FIXED_RAW_TOKEN = b"\x01" * 32
FIXED_TOKEN_HEX = FIXED_RAW_TOKEN.hex()
FIXED_TOKEN_HASH = hashlib.sha256(FIXED_RAW_TOKEN).hexdigest()


# Real os.urandom reference saved before any patching
_real_urandom = os.urandom


def _urandom_side_effect(n: int) -> bytes:
    """
    Side effect for patching agencies.views.os.urandom.
    Returns FIXED_RAW_TOKEN when n==32 (the token generation call),
    and real random bytes for all other sizes (e.g., uuid4 calls os.urandom(16)).
    Uses the saved reference to avoid infinite recursion.
    """
    if n == 32:
        return FIXED_RAW_TOKEN
    return _real_urandom(n)


# ===========================================================================
# TestAgencyRegistration
# Requirements: 1.4–1.8, 2.1, 2.2, 2.7
# ===========================================================================

class TestAgencyRegistration(TestCase):
    """
    Tests for POST /api/v1/agencies/register/

    Validates: Requirements 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.7
    """

    def setUp(self):
        self.client = Client()

    @patch("agencies.tasks.send_verification_email")
    def test_successful_registration_creates_agency_and_user(self, mock_task):
        """
        POST valid payload → 201, Agency created with PENDING_APPROVAL,
        User created with is_active=False and role=AGENCY_ADMIN,
        EmailVerificationToken created, AGENCY_REGISTERED AuditLog entry written.

        Validates: Requirements 1.4, 2.1, 2.2
        """
        mock_task.delay = MagicMock()
        payload = _valid_payload()

        response = self.client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        # Agency created with PENDING_APPROVAL
        agency = Agency.objects.get(gstin=payload["gstin"])
        self.assertEqual(agency.status, AgencyStatus.PENDING_APPROVAL)
        self.assertEqual(agency.legal_name, payload["legal_name"])

        # User created with is_active=False and role=AGENCY_ADMIN
        user = User.objects.get(email=payload["contact_email"])
        self.assertFalse(user.is_active)
        self.assertEqual(user.role, UserRole.AGENCY_ADMIN)
        self.assertEqual(user.agency, agency)

        # EmailVerificationToken created
        self.assertTrue(
            EmailVerificationToken.objects.filter(user=user).exists()
        )

        # AGENCY_REGISTERED AuditLog entry written
        self.assertTrue(
            AuditLog.objects.filter(
                event_type=EventType.AGENCY_REGISTERED,
                user=user,
            ).exists()
        )

    @patch("agencies.tasks.send_verification_email")
    def test_registration_missing_required_field_returns_400(self, mock_task):
        """
        POST with missing `gstin` → 400 with missing_fields in response.

        Validates: Requirement 1.7
        """
        mock_task.delay = MagicMock()
        payload = _valid_payload()
        del payload["gstin"]

        response = self.client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("missing_fields", data)
        self.assertIn("gstin", data["missing_fields"])

    @patch("agencies.tasks.send_verification_email")
    def test_registration_duplicate_gstin_returns_400(self, mock_task):
        """
        POST same GSTIN twice → second returns 400 with "already registered" message.

        Validates: Requirement 1.5
        """
        mock_task.delay = MagicMock()
        payload = _valid_payload()

        # First registration succeeds
        response1 = self.client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response1.status_code, 201)

        # Second registration with same GSTIN but different email
        payload2 = _valid_payload(
            gstin=payload["gstin"],
            contact_email=f"other-{uuid.uuid4().hex[:8]}@example.com",
        )
        response2 = self.client.post(
            REGISTER_URL,
            data=json.dumps(payload2),
            content_type="application/json",
        )

        self.assertEqual(response2.status_code, 400)
        data = response2.json()
        self.assertIn("already registered", data.get("detail", "").lower())

    @patch("agencies.tasks.send_verification_email")
    def test_registration_duplicate_email_returns_400(self, mock_task):
        """
        POST same email twice → second returns 400 with "already associated" message.

        Validates: Requirement 1.6
        """
        mock_task.delay = MagicMock()
        payload = _valid_payload()

        # First registration succeeds
        response1 = self.client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response1.status_code, 201)

        # Second registration with same email but different GSTIN
        payload2 = _valid_payload(contact_email=payload["contact_email"])
        response2 = self.client.post(
            REGISTER_URL,
            data=json.dumps(payload2),
            content_type="application/json",
        )

        self.assertEqual(response2.status_code, 400)
        data = response2.json()
        self.assertIn("already associated", data.get("detail", "").lower())

    @patch("agencies.tasks.send_verification_email")
    def test_registration_invalid_gstin_format_returns_400(self, mock_task):
        """
        POST with GSTIN "INVALID" → 400.

        Validates: Requirement 2.7
        """
        mock_task.delay = MagicMock()
        payload = _valid_payload(gstin="INVALID")

        response = self.client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    @patch("agencies.tasks.send_verification_email")
    def test_registration_enqueues_verification_email_task(self, mock_task):
        """
        POST valid payload → `send_verification_email.delay` called once
        with correct user_id and agency_name.

        Validates: Requirement 1.8
        """
        mock_delay = MagicMock()
        mock_task.delay = mock_delay
        payload = _valid_payload()

        response = self.client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        mock_delay.assert_called_once()

        call_args = mock_delay.call_args
        user_id_arg = call_args[0][0]
        agency_name_arg = call_args[0][2]

        user = User.objects.get(email=payload["contact_email"])
        self.assertEqual(user_id_arg, user.pk)
        self.assertEqual(agency_name_arg, payload["legal_name"])


# ===========================================================================
# TestEmailVerification
# Requirements: 1.9, 2.3
# ===========================================================================

class TestEmailVerification(TestCase):
    """
    Tests for GET /api/v1/agencies/verify-email/?token=<hex>

    Validates: Requirements 1.9, 2.3
    """

    def setUp(self):
        self.client = Client()

    def _register_agency(self):
        """
        Register an agency with a fixed os.urandom so we know the token_hex.
        Returns (user, agency, token_hex).
        """
        payload = _valid_payload()
        with patch("agencies.views.os.urandom", side_effect=_urandom_side_effect), \
             patch("agencies.tasks.send_verification_email") as mock_task:
            mock_task.delay = MagicMock()
            response = self.client.post(
                REGISTER_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email=payload["contact_email"])
        agency = user.agency
        return user, agency, FIXED_TOKEN_HEX

    def test_valid_token_activates_user_and_agency(self):
        """
        GET with valid token → 200, User.is_active=True, User.email_verified=True,
        Agency.status=ACTIVE, Agency.approved_at set,
        AGENCY_STATUS_CHANGED AuditLog entry written.

        Validates: Requirements 1.9, 2.3
        """
        user, agency, token_hex = self._register_agency()

        response = self.client.get(
            VERIFY_URL,
            {"token": token_hex},
        )

        self.assertEqual(response.status_code, 200)

        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertTrue(user.email_verified)

        agency.refresh_from_db()
        self.assertEqual(agency.status, AgencyStatus.ACTIVE)
        self.assertIsNotNone(agency.approved_at)

        self.assertTrue(
            AuditLog.objects.filter(
                event_type=EventType.AGENCY_STATUS_CHANGED,
                user=user,
            ).exists()
        )

    def test_expired_token_returns_400(self):
        """
        GET with token whose expires_at is in the past → 400.

        Validates: Requirement 1.9
        """
        user, agency, token_hex = self._register_agency()

        # Force the token to be expired
        token = EmailVerificationToken.objects.get(user=user)
        token.expires_at = timezone.now() - timezone.timedelta(hours=1)
        token.save(update_fields=["expires_at"])

        response = self.client.get(
            VERIFY_URL,
            {"token": token_hex},
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_token_hex_returns_400(self):
        """
        GET with token="notvalidhex" → 400.

        Validates: Requirement 1.9
        """
        response = self.client.get(
            VERIFY_URL,
            {"token": "notvalidhex"},
        )

        self.assertEqual(response.status_code, 400)

    def test_unknown_token_returns_400(self):
        """
        GET with valid hex but no matching record → 400.

        Validates: Requirement 1.9
        """
        unknown_hex = (b"\xab" * 32).hex()

        response = self.client.get(
            VERIFY_URL,
            {"token": unknown_hex},
        )

        self.assertEqual(response.status_code, 400)

    def test_token_is_deleted_after_verification(self):
        """
        GET with valid token → EmailVerificationToken record is deleted from DB.

        Validates: Requirement 1.9
        """
        user, agency, token_hex = self._register_agency()

        self.assertTrue(
            EmailVerificationToken.objects.filter(user=user).exists()
        )

        response = self.client.get(
            VERIFY_URL,
            {"token": token_hex},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            EmailVerificationToken.objects.filter(user=user).exists()
        )


# ===========================================================================
# TestAgencyLogin
# Requirements: 9.1–9.3, 9.5, 9.6, 9.7
# ===========================================================================

class TestAgencyLogin(TestCase):
    """
    Tests for POST /api/v1/agencies/login/

    Validates: Requirements 9.1, 9.2, 9.3, 9.5, 9.6, 9.7
    """

    def setUp(self):
        self.client = Client()
        self.password = "SecurePass123!"

    def _register_and_verify(self, password=None):
        """
        Register an agency and verify the email. Returns (user, agency, email, password).
        """
        password = password or self.password
        payload = _valid_payload(password=password)
        email = payload["contact_email"]

        with patch("agencies.views.os.urandom", side_effect=_urandom_side_effect), \
             patch("agencies.tasks.send_verification_email") as mock_task:
            mock_task.delay = MagicMock()
            reg_response = self.client.post(
                REGISTER_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(reg_response.status_code, 201)

        # Verify email
        verify_response = self.client.get(
            VERIFY_URL,
            {"token": FIXED_TOKEN_HEX},
        )
        self.assertEqual(verify_response.status_code, 200)

        user = User.objects.get(email=email)
        agency = user.agency
        return user, agency, email, password

    def test_successful_login_returns_jwt_with_claims(self):
        """
        Register + verify + POST /login → 200, response contains `access`,
        `refresh`, `role`="AGENCY_ADMIN", `agency_id` matching the agency's UUID.

        Validates: Requirements 9.1, 9.2, 9.3
        """
        user, agency, email, password = self._register_and_verify()

        response = self.client.post(
            LOGIN_URL,
            data=json.dumps({"email": email, "password": password}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["role"], UserRole.AGENCY_ADMIN)
        self.assertEqual(data["agency_id"], str(agency.agency_id))

    def test_login_with_wrong_password_returns_401(self):
        """
        POST /login with wrong password → 401, failed_attempts incremented.

        Validates: Requirement 9.5
        """
        user, agency, email, password = self._register_and_verify()

        response = self.client.post(
            LOGIN_URL,
            data=json.dumps({"email": email, "password": "WrongPassword!"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

        user.refresh_from_db()
        self.assertEqual(user.failed_login_attempts, 1)

    def test_login_with_unverified_account_returns_401(self):
        """
        Register but do NOT verify → POST /login → 401
        (user is_active=False, Django authenticate returns None).

        Validates: Requirement 9.1
        """
        payload = _valid_payload()
        email = payload["contact_email"]
        password = payload["password"]

        with patch("agencies.tasks.send_verification_email") as mock_task:
            mock_task.delay = MagicMock()
            reg_response = self.client.post(
                REGISTER_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )
        self.assertEqual(reg_response.status_code, 201)

        # Do NOT verify — user is_active=False
        response = self.client.post(
            LOGIN_URL,
            data=json.dumps({"email": email, "password": password}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

    def test_login_with_suspended_agency_returns_403(self):
        """
        Register + verify + set agency.status=SUSPENDED + POST /login → 403
        with "suspended" message.

        Validates: Requirement 9.7
        """
        user, agency, email, password = self._register_and_verify()

        agency.status = AgencyStatus.SUSPENDED
        agency.save(update_fields=["status"])

        response = self.client.post(
            LOGIN_URL,
            data=json.dumps({"email": email, "password": password}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("suspended", data.get("detail", "").lower())

    def test_account_lockout_after_5_failed_attempts(self):
        """
        POST /login with wrong password 5 times → 6th attempt returns 403
        with locked_until in response, USER_LOCKED AuditLog entry written.

        Validates: Requirements 9.5, 9.6
        """
        user, agency, email, password = self._register_and_verify()

        # 5 failed attempts
        for _ in range(5):
            self.client.post(
                LOGIN_URL,
                data=json.dumps({"email": email, "password": "WrongPassword!"}),
                content_type="application/json",
            )

        # 6th attempt — account should now be locked
        response = self.client.post(
            LOGIN_URL,
            data=json.dumps({"email": email, "password": "WrongPassword!"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("locked_until", data)

        # USER_LOCKED AuditLog entry written
        self.assertTrue(
            AuditLog.objects.filter(
                event_type=EventType.USER_LOCKED,
                user=user,
            ).exists()
        )

    def test_locked_account_returns_403_before_lockout_expires(self):
        """
        Lock account, then immediately try again → 403 with locked_until.

        Validates: Requirement 9.5
        """
        user, agency, email, password = self._register_and_verify()

        # Trigger lockout with 5 failed attempts
        for _ in range(5):
            self.client.post(
                LOGIN_URL,
                data=json.dumps({"email": email, "password": "WrongPassword!"}),
                content_type="application/json",
            )

        # Immediately try with correct password — still locked
        response = self.client.post(
            LOGIN_URL,
            data=json.dumps({"email": email, "password": password}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("locked_until", data)

    def test_login_writes_audit_log_on_success(self):
        """
        Successful login → USER_LOGIN AuditLog entry with correct user_id,
        agency_id, role.

        Validates: Requirement 9.3
        """
        user, agency, email, password = self._register_and_verify()

        self.client.post(
            LOGIN_URL,
            data=json.dumps({"email": email, "password": password}),
            content_type="application/json",
        )

        log = AuditLog.objects.filter(
            event_type=EventType.USER_LOGIN,
            user=user,
        ).first()

        self.assertIsNotNone(log)
        self.assertEqual(log.data_snapshot.get("role"), UserRole.AGENCY_ADMIN)
        self.assertEqual(
            log.data_snapshot.get("agency_id"),
            str(agency.pk),
        )


# ===========================================================================
# TestFullRegistrationToLoginFlow
# Requirements: 1.4–1.9, 2.1–2.3, 9.1–9.3
# ===========================================================================

class TestFullRegistrationToLoginFlow(TestCase):
    """
    End-to-end integration test: register → verify → login.

    Validates: Requirements 1.4–1.9, 2.1–2.3, 9.1–9.3
    """

    def setUp(self):
        self.client = Client()

    def test_full_flow_register_verify_login(self):
        """
        Complete end-to-end:
          1. Register → 201
          2. Extract token_hex from EmailVerificationToken DB record
          3. Verify → 200, user activated, agency ACTIVE
          4. Login → 200, JWT claims are correct

        Validates: Requirements 1.4–1.9, 2.1–2.3, 9.1–9.3
        """
        password = "SecurePass123!"
        payload = _valid_payload(password=password)
        email = payload["contact_email"]

        # Step 1: Register
        with patch("agencies.views.os.urandom", side_effect=_urandom_side_effect), \
             patch("agencies.tasks.send_verification_email") as mock_task:
            mock_task.delay = MagicMock()
            reg_response = self.client.post(
                REGISTER_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )

        self.assertEqual(reg_response.status_code, 201)

        # Confirm user is inactive and agency is pending
        user = User.objects.get(email=email)
        self.assertFalse(user.is_active)
        self.assertEqual(user.agency.status, AgencyStatus.PENDING_APPROVAL)

        # Step 2: Extract token_hex — we patched os.urandom so we know it
        token_hex = FIXED_TOKEN_HEX

        # Confirm the token record exists in the DB
        token_record = EmailVerificationToken.objects.get(user=user)
        self.assertEqual(token_record.token_hash, FIXED_TOKEN_HASH)

        # Step 3: Verify email
        verify_response = self.client.get(
            VERIFY_URL,
            {"token": token_hex},
        )
        self.assertEqual(verify_response.status_code, 200)

        user.refresh_from_db()
        agency = user.agency
        agency.refresh_from_db()

        self.assertTrue(user.is_active)
        self.assertTrue(user.email_verified)
        self.assertEqual(agency.status, AgencyStatus.ACTIVE)
        self.assertIsNotNone(agency.approved_at)

        # Token should be deleted
        self.assertFalse(
            EmailVerificationToken.objects.filter(user=user).exists()
        )

        # Step 4: Login
        login_response = self.client.post(
            LOGIN_URL,
            data=json.dumps({"email": email, "password": password}),
            content_type="application/json",
        )

        self.assertEqual(login_response.status_code, 200)
        data = login_response.json()

        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["role"], UserRole.AGENCY_ADMIN)
        self.assertEqual(data["agency_id"], str(agency.agency_id))
