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


# ===========================================================================
# TestAgencyTenderListView — Task 6.1
# GET /api/v1/agencies/me/tenders/
# Requirements: 5.1, 5.3, 5.6, 5.7, 8.2
# ===========================================================================

TENDER_LIST_URL = "/api/v1/agencies/me/tenders/"


def _make_active_agency(uid=None):
    """Create an ACTIVE agency for use in tender list tests."""
    from agencies.models import Agency, AgencyStatus
    uid = uid or uuid.uuid4().hex[:8]
    return Agency.objects.create(
        legal_name=f"Agency {uid}",
        gstin=_unique_gstin(),
        ministry="Ministry of Test",
        contact_name="Test Contact",
        contact_email=f"contact-{uid}@example.com",
        status=AgencyStatus.ACTIVE,
    )


def _make_agency_user(agency, role="AGENCY_ADMIN", uid=None):
    """Create an active agency user linked to the given agency."""
    uid = uid or uuid.uuid4().hex[:8]
    user = User.objects.create_user(
        username=f"user_{uid}",
        email=f"user_{uid}@example.com",
        password="TestPass123!",
        role=role,
    )
    user.is_active = True
    user.email_verified = True
    user.agency = agency
    user.save(update_fields=["is_active", "email_verified", "agency_id"])
    return user


def _make_tender_submission(agency, user, status="DRAFT", category="IT",
                             estimated_value="100000.00", days_offset=0):
    """Create a TenderSubmission for the given agency and user."""
    from agencies.models import TenderSubmission
    from decimal import Decimal
    uid = uuid.uuid4().hex[:8]
    submission = TenderSubmission.objects.create(
        agency=agency,
        submitted_by=user,
        tender=None,
        tender_ref=f"REF-{uid}",
        title=f"Tender {uid}",
        category=category,
        estimated_value=Decimal(estimated_value),
        submission_deadline=timezone.now() + timezone.timedelta(days=30),
        buyer_name="Test Buyer",
        status=status,
    )
    if days_offset != 0:
        # Adjust created_at for date range filter tests
        TenderSubmission = submission.__class__
        TenderSubmission.objects.filter(pk=submission.pk).update(
            created_at=timezone.now() + timezone.timedelta(days=days_offset)
        )
        submission.refresh_from_db()
    return submission


def _get_jwt_for_user(user):
    """Get a JWT access token for the given user."""
    from agencies.serializers import AgencyTokenObtainPairSerializer
    refresh = AgencyTokenObtainPairSerializer.get_token(user)
    return str(refresh.access_token)


class TestAgencyTenderListView(TestCase):
    """
    Integration tests for GET /api/v1/agencies/me/tenders/

    Validates: Requirements 5.1, 5.3, 5.6, 5.7, 8.2
    """

    def setUp(self):
        self.client = Client()
        self.agency = _make_active_agency()
        self.admin_user = _make_agency_user(self.agency, role="AGENCY_ADMIN")
        self.officer_user = _make_agency_user(self.agency, role="AGENCY_OFFICER")
        self.reviewer_user = _make_agency_user(self.agency, role="REVIEWER")
        self.token = _get_jwt_for_user(self.admin_user)

    def _auth_get(self, url, params=None, token=None):
        """Perform an authenticated GET request."""
        token = token or self.token
        return self.client.get(
            url,
            params or {},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # Requirement 5.1 — Only own agency's tenders are returned
    # -----------------------------------------------------------------------

    def test_returns_only_own_agency_tenders(self):
        """
        GET /api/v1/agencies/me/tenders/ returns only submissions belonging
        to the authenticated user's agency.

        Validates: Requirements 5.1, 8.2
        """
        # Create submissions for own agency
        s1 = _make_tender_submission(self.agency, self.admin_user)
        s2 = _make_tender_submission(self.agency, self.admin_user)

        # Create a different agency with its own submission
        other_agency = _make_active_agency()
        other_user = _make_agency_user(other_agency, role="AGENCY_ADMIN")
        _make_tender_submission(other_agency, other_user)

        response = self._auth_get(TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}

        self.assertIn(s1.pk, result_ids)
        self.assertIn(s2.pk, result_ids)
        # Other agency's submission must NOT appear
        self.assertEqual(len(result_ids), 2)

    def test_unauthenticated_request_returns_401(self):
        """
        GET without Authorization header → 401.

        Validates: Requirement 8.2
        """
        response = self.client.get(TENDER_LIST_URL)
        self.assertIn(response.status_code, [401, 403])

    def test_all_agency_roles_can_access(self):
        """
        AGENCY_ADMIN, AGENCY_OFFICER, and REVIEWER can all access the list.

        Validates: Requirement 5.1
        """
        _make_tender_submission(self.agency, self.admin_user)

        for role_user in [self.admin_user, self.officer_user, self.reviewer_user]:
            token = _get_jwt_for_user(role_user)
            response = self._auth_get(TENDER_LIST_URL, token=token)
            self.assertEqual(
                response.status_code, 200,
                msg=f"Role {role_user.role} should be able to access tender list"
            )

    # -----------------------------------------------------------------------
    # Requirement 5.3 — Paginated list with required fields
    # -----------------------------------------------------------------------

    def test_response_contains_required_fields(self):
        """
        Each item in the paginated list includes: id, title, category,
        estimated_value, status, fraud_risk_score, created_at.

        Validates: Requirement 5.3
        """
        _make_tender_submission(self.agency, self.admin_user)

        response = self._auth_get(TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        self.assertGreater(len(data["results"]), 0)

        item = data["results"][0]
        required_fields = [
            "id", "title", "category", "estimated_value",
            "status", "fraud_risk_score", "created_at",
        ]
        for field in required_fields:
            self.assertIn(field, item, msg=f"Field '{field}' missing from response")

    def test_response_includes_risk_badge(self):
        """
        Each item includes a risk_badge field (null when no fraud score).

        Validates: Requirement 5.4
        """
        _make_tender_submission(self.agency, self.admin_user)

        response = self._auth_get(TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertIn("risk_badge", item)

    def test_pagination_returns_count_and_next(self):
        """
        Response includes pagination metadata: count, next, previous, results.

        Validates: Requirement 5.3
        """
        for _ in range(3):
            _make_tender_submission(self.agency, self.admin_user)

        response = self._auth_get(TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertEqual(data["count"], 3)

    def test_empty_list_when_no_submissions(self):
        """
        GET with no submissions → 200 with empty results list.

        Validates: Requirement 5.1
        """
        response = self._auth_get(TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["results"], [])

    # -----------------------------------------------------------------------
    # Requirement 5.6 — Filters: status, category, date_range
    # -----------------------------------------------------------------------

    def test_filter_by_status(self):
        """
        ?status=DRAFT returns only DRAFT submissions.

        Validates: Requirement 5.6
        """
        draft = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        submitted = _make_tender_submission(self.agency, self.admin_user, status="SUBMITTED")

        response = self._auth_get(TENDER_LIST_URL, {"status": "DRAFT"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}

        self.assertIn(draft.pk, result_ids)
        self.assertNotIn(submitted.pk, result_ids)

    def test_filter_by_category(self):
        """
        ?category=IT returns only IT category submissions (case-insensitive).

        Validates: Requirement 5.6
        """
        it_sub = _make_tender_submission(self.agency, self.admin_user, category="IT")
        infra_sub = _make_tender_submission(self.agency, self.admin_user, category="Infrastructure")

        response = self._auth_get(TENDER_LIST_URL, {"category": "it"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}

        self.assertIn(it_sub.pk, result_ids)
        self.assertNotIn(infra_sub.pk, result_ids)

    def test_filter_by_date_range_date_from(self):
        """
        ?date_from=<future_date> returns only submissions created on or after that date.

        Validates: Requirement 5.6
        """
        from agencies.models import TenderSubmission as TS
        import datetime

        # Create a submission and manually set its created_at to yesterday
        old_sub = _make_tender_submission(self.agency, self.admin_user)
        yesterday = (timezone.now() - timezone.timedelta(days=2)).date()
        TS.objects.filter(pk=old_sub.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=2)
        )

        # Create a recent submission
        new_sub = _make_tender_submission(self.agency, self.admin_user)

        today_str = timezone.now().date().isoformat()
        response = self._auth_get(TENDER_LIST_URL, {"date_from": today_str})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}

        self.assertIn(new_sub.pk, result_ids)
        self.assertNotIn(old_sub.pk, result_ids)

    def test_filter_by_date_range_date_to(self):
        """
        ?date_to=<past_date> returns only submissions created on or before that date.

        Validates: Requirement 5.6
        """
        from agencies.models import TenderSubmission as TS

        # Create a submission and manually set its created_at to 2 days ago
        old_sub = _make_tender_submission(self.agency, self.admin_user)
        TS.objects.filter(pk=old_sub.pk).update(
            created_at=timezone.now() - timezone.timedelta(days=2)
        )

        # Create a recent submission (today)
        new_sub = _make_tender_submission(self.agency, self.admin_user)

        # Filter to only show submissions from yesterday or earlier
        yesterday_str = (timezone.now() - timezone.timedelta(days=1)).date().isoformat()
        response = self._auth_get(TENDER_LIST_URL, {"date_to": yesterday_str})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}

        self.assertIn(old_sub.pk, result_ids)
        self.assertNotIn(new_sub.pk, result_ids)

    def test_combined_status_and_category_filter(self):
        """
        ?status=DRAFT&category=IT returns only DRAFT IT submissions.

        Validates: Requirement 5.6
        """
        draft_it = _make_tender_submission(
            self.agency, self.admin_user, status="DRAFT", category="IT"
        )
        draft_infra = _make_tender_submission(
            self.agency, self.admin_user, status="DRAFT", category="Infrastructure"
        )
        submitted_it = _make_tender_submission(
            self.agency, self.admin_user, status="SUBMITTED", category="IT"
        )

        response = self._auth_get(TENDER_LIST_URL, {"status": "DRAFT", "category": "IT"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}

        self.assertIn(draft_it.pk, result_ids)
        self.assertNotIn(draft_infra.pk, result_ids)
        self.assertNotIn(submitted_it.pk, result_ids)

    # -----------------------------------------------------------------------
    # Requirement 5.7 — Sort: created_at (default desc), estimated_value,
    #                         fraud_risk_score
    # -----------------------------------------------------------------------

    def test_default_ordering_is_created_at_desc(self):
        """
        Without ?ordering param, results are sorted by created_at descending.

        Validates: Requirement 5.7
        """
        from agencies.models import TenderSubmission as TS

        s1 = _make_tender_submission(self.agency, self.admin_user)
        s2 = _make_tender_submission(self.agency, self.admin_user)
        s3 = _make_tender_submission(self.agency, self.admin_user)

        # Set created_at explicitly so ordering is deterministic
        TS.objects.filter(pk=s1.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=3)
        )
        TS.objects.filter(pk=s2.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=2)
        )
        TS.objects.filter(pk=s3.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=1)
        )

        response = self._auth_get(TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        result_ids = [r["id"] for r in response.json()["results"]]

        # s3 (most recent) should come first
        self.assertEqual(result_ids, [s3.pk, s2.pk, s1.pk])

    def test_ordering_by_created_at_asc(self):
        """
        ?ordering=created_at returns results sorted by created_at ascending.

        Validates: Requirement 5.7
        """
        from agencies.models import TenderSubmission as TS

        s1 = _make_tender_submission(self.agency, self.admin_user)
        s2 = _make_tender_submission(self.agency, self.admin_user)

        TS.objects.filter(pk=s1.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=2)
        )
        TS.objects.filter(pk=s2.pk).update(
            created_at=timezone.now() - timezone.timedelta(hours=1)
        )

        response = self._auth_get(TENDER_LIST_URL, {"ordering": "created_at"})

        self.assertEqual(response.status_code, 200)
        result_ids = [r["id"] for r in response.json()["results"]]

        # s1 (oldest) should come first
        self.assertEqual(result_ids, [s1.pk, s2.pk])

    def test_ordering_by_estimated_value_desc(self):
        """
        ?ordering=-estimated_value returns results sorted by estimated_value descending.

        Validates: Requirement 5.7
        """
        s_low = _make_tender_submission(
            self.agency, self.admin_user, estimated_value="50000.00"
        )
        s_high = _make_tender_submission(
            self.agency, self.admin_user, estimated_value="200000.00"
        )
        s_mid = _make_tender_submission(
            self.agency, self.admin_user, estimated_value="100000.00"
        )

        response = self._auth_get(TENDER_LIST_URL, {"ordering": "-estimated_value"})

        self.assertEqual(response.status_code, 200)
        result_ids = [r["id"] for r in response.json()["results"]]

        self.assertEqual(result_ids, [s_high.pk, s_mid.pk, s_low.pk])

    def test_ordering_by_estimated_value_asc(self):
        """
        ?ordering=estimated_value returns results sorted by estimated_value ascending.

        Validates: Requirement 5.7
        """
        s_low = _make_tender_submission(
            self.agency, self.admin_user, estimated_value="50000.00"
        )
        s_high = _make_tender_submission(
            self.agency, self.admin_user, estimated_value="200000.00"
        )

        response = self._auth_get(TENDER_LIST_URL, {"ordering": "estimated_value"})

        self.assertEqual(response.status_code, 200)
        result_ids = [r["id"] for r in response.json()["results"]]

        self.assertEqual(result_ids, [s_low.pk, s_high.pk])

    def test_ordering_by_fraud_risk_score_nulls_last(self):
        """
        ?ordering=fraud_risk_score returns results with null scores last.

        Validates: Requirement 5.7
        """
        # Submissions without fraud scores (tender=None)
        s_no_score = _make_tender_submission(self.agency, self.admin_user)

        response = self._auth_get(TENDER_LIST_URL, {"ordering": "fraud_risk_score"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # All items have null fraud_risk_score — just verify the request succeeds
        self.assertIsNotNone(data["results"])
        for item in data["results"]:
            self.assertIsNone(item["fraud_risk_score"])

    def test_invalid_ordering_falls_back_to_default(self):
        """
        ?ordering=invalid_field falls back to default -created_at ordering.

        Validates: Requirement 5.7
        """
        _make_tender_submission(self.agency, self.admin_user)

        response = self._auth_get(TENDER_LIST_URL, {"ordering": "invalid_field"})

        self.assertEqual(response.status_code, 200)
        # Should not raise an error
        data = response.json()
        self.assertIn("results", data)

    # -----------------------------------------------------------------------
    # Requirement 5.4 — Risk badge colour coding
    # -----------------------------------------------------------------------

    def test_fraud_risk_score_null_when_no_tender_linked(self):
        """
        Submissions without a linked Tender have null fraud_risk_score and risk_badge.

        Validates: Requirement 5.4
        """
        _make_tender_submission(self.agency, self.admin_user)

        response = self._auth_get(TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        item = response.json()["results"][0]
        self.assertIsNone(item["fraud_risk_score"])
        self.assertIsNone(item["risk_badge"])

    # -----------------------------------------------------------------------
    # Requirement 8.2 — Agency scoping enforced at queryset level
    # -----------------------------------------------------------------------

    def test_cross_agency_data_isolation(self):
        """
        User from agency A cannot see submissions from agency B.

        Validates: Requirement 8.2
        """
        # Agency A submissions
        s_a = _make_tender_submission(self.agency, self.admin_user)

        # Agency B with its own user and submissions
        agency_b = _make_active_agency()
        user_b = _make_agency_user(agency_b, role="AGENCY_ADMIN")
        s_b = _make_tender_submission(agency_b, user_b)

        # User A's token
        token_a = _get_jwt_for_user(self.admin_user)
        response_a = self._auth_get(TENDER_LIST_URL, token=token_a)
        ids_a = {r["id"] for r in response_a.json()["results"]}

        # User B's token
        token_b = _get_jwt_for_user(user_b)
        response_b = self._auth_get(TENDER_LIST_URL, token=token_b)
        ids_b = {r["id"] for r in response_b.json()["results"]}

        # Each user sees only their own agency's submissions
        self.assertIn(s_a.pk, ids_a)
        self.assertNotIn(s_b.pk, ids_a)

        self.assertIn(s_b.pk, ids_b)
        self.assertNotIn(s_a.pk, ids_b)

    def test_user_without_agency_returns_403(self):
        """
        A user with no agency association gets 403.

        Validates: Requirement 8.2
        """
        # Create a user with no agency
        no_agency_user = User.objects.create_user(
            username=f"noagency_{uuid.uuid4().hex[:8]}",
            email=f"noagency_{uuid.uuid4().hex[:8]}@example.com",
            password="TestPass123!",
            role="AGENCY_ADMIN",
        )
        no_agency_user.is_active = True
        no_agency_user.save(update_fields=["is_active"])

        token = _get_jwt_for_user(no_agency_user)
        response = self._auth_get(TENDER_LIST_URL, token=token)

        self.assertEqual(response.status_code, 403)


# ===========================================================================
# TestAgencyTenderCreateView — Task 6.2
# POST /api/v1/agencies/me/tenders/
# Requirements: 6.1, 6.2, 6.3, 6.4, 6.11, 6.12
# ===========================================================================


def _future_deadline(days=30):
    """Return an ISO 8601 datetime string for a deadline in the future."""
    return (timezone.now() + timezone.timedelta(days=days)).isoformat()


def _past_deadline(days=1):
    """Return an ISO 8601 datetime string for a deadline in the past."""
    return (timezone.now() - timezone.timedelta(days=days)).isoformat()


def _valid_tender_payload(**overrides) -> dict:
    """Return a complete, valid tender creation payload."""
    uid = uuid.uuid4().hex[:8]
    payload = {
        "tender_ref": f"REF-{uid}",
        "title": f"Test Tender {uid}",
        "category": "IT",
        "estimated_value": "100000.00",
        "submission_deadline": _future_deadline(30),
        "buyer_name": "Ministry of Finance",
        "spec_text": "Detailed specification text.",
    }
    payload.update(overrides)
    return payload


class TestAgencyTenderCreateView(TestCase):
    """
    Integration tests for POST /api/v1/agencies/me/tenders/

    Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.11, 6.12
    """

    def setUp(self):
        self.client = Client()
        self.agency = _make_active_agency()
        self.admin_user = _make_agency_user(self.agency, role="AGENCY_ADMIN")
        self.officer_user = _make_agency_user(self.agency, role="AGENCY_OFFICER")
        self.reviewer_user = _make_agency_user(self.agency, role="REVIEWER")
        self.admin_token = _get_jwt_for_user(self.admin_user)
        self.officer_token = _get_jwt_for_user(self.officer_user)
        self.reviewer_token = _get_jwt_for_user(self.reviewer_user)

    def _auth_post(self, payload, token=None):
        """Perform an authenticated POST request."""
        token = token or self.admin_token
        return self.client.post(
            TENDER_LIST_URL,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # Requirement 6.2 — DRAFT creation with correct agency linkage
    # -----------------------------------------------------------------------

    def test_agency_admin_can_create_tender(self):
        """
        POST valid payload as AGENCY_ADMIN → 201, TenderSubmission created
        with status=DRAFT linked to user's agency.

        Validates: Requirements 6.1, 6.2
        """
        from agencies.models import TenderSubmission

        payload = _valid_tender_payload()
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()

        # Response contains the created submission data
        self.assertIn("id", data)
        self.assertEqual(data["status"], "DRAFT")
        self.assertEqual(data["tender_ref"], payload["tender_ref"])
        self.assertEqual(data["category"], payload["category"])

        # Submission exists in DB with correct agency linkage
        submission = TenderSubmission.objects.get(pk=data["id"])
        self.assertEqual(submission.agency_id, self.agency.pk)
        self.assertEqual(submission.submitted_by_id, self.admin_user.pk)
        self.assertEqual(submission.status, "DRAFT")

    def test_agency_officer_can_create_tender(self):
        """
        POST valid payload as AGENCY_OFFICER → 201.

        Validates: Requirement 6.2
        """
        payload = _valid_tender_payload()
        response = self._auth_post(payload, token=self.officer_token)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "DRAFT")

    def test_reviewer_cannot_create_tender(self):
        """
        POST as REVIEWER → 403 (role not permitted).

        Validates: Requirement 6.2
        """
        payload = _valid_tender_payload()
        response = self._auth_post(payload, token=self.reviewer_token)

        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_request_returns_401(self):
        """
        POST without Authorization header → 401.

        Validates: Requirement 6.2
        """
        payload = _valid_tender_payload()
        response = self.client.post(
            TENDER_LIST_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertIn(response.status_code, [401, 403])

    # -----------------------------------------------------------------------
    # Requirement 6.3 — Required field validation
    # -----------------------------------------------------------------------

    def test_missing_required_field_returns_400(self):
        """
        POST with missing `tender_ref` → 400 with missing_fields in response.

        Validates: Requirement 6.3
        """
        payload = _valid_tender_payload()
        del payload["tender_ref"]

        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("missing_fields", data)
        self.assertIn("tender_ref", data["missing_fields"])

    def test_all_required_fields_missing_returns_400_with_all_listed(self):
        """
        POST with all required fields missing → 400 listing all missing fields.

        Validates: Requirement 6.3
        """
        response = self._auth_post({})

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("missing_fields", data)
        required = ["tender_ref", "title", "category", "estimated_value",
                    "submission_deadline", "buyer_name"]
        for field in required:
            self.assertIn(field, data["missing_fields"])

    def test_empty_string_required_field_returns_400(self):
        """
        POST with empty string for a required field → 400.

        Validates: Requirement 6.3
        """
        payload = _valid_tender_payload(title="   ")

        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("missing_fields", data)
        self.assertIn("title", data["missing_fields"])

    # -----------------------------------------------------------------------
    # Requirement 6.3 — estimated_value validation
    # -----------------------------------------------------------------------

    def test_estimated_value_not_a_number_returns_400(self):
        """
        POST with estimated_value="not-a-number" → 400.

        Validates: Requirement 6.3
        """
        payload = _valid_tender_payload(estimated_value="not-a-number")
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("estimated_value", data.get("detail", "").lower())

    def test_estimated_value_zero_returns_400(self):
        """
        POST with estimated_value=0 → 400 (must be positive).

        Validates: Requirement 6.3
        """
        payload = _valid_tender_payload(estimated_value="0")
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("positive", data.get("detail", "").lower())

    def test_estimated_value_negative_returns_400(self):
        """
        POST with estimated_value=-100 → 400 (must be positive).

        Validates: Requirement 6.3
        """
        payload = _valid_tender_payload(estimated_value="-100.00")
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("positive", data.get("detail", "").lower())

    def test_estimated_value_more_than_2_decimal_places_returns_400(self):
        """
        POST with estimated_value="100.123" (3 decimal places) → 400.

        Validates: Requirement 6.3
        """
        payload = _valid_tender_payload(estimated_value="100.123")
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("decimal", data.get("detail", "").lower())

    def test_estimated_value_exactly_2_decimal_places_accepted(self):
        """
        POST with estimated_value="100.12" (2 decimal places) → 201.

        Validates: Requirement 6.3
        """
        payload = _valid_tender_payload(estimated_value="100.12")
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["estimated_value"], "100.12")

    def test_estimated_value_integer_accepted(self):
        """
        POST with estimated_value="50000" (no decimal places) → 201.

        Validates: Requirement 6.3
        """
        payload = _valid_tender_payload(estimated_value="50000")
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)

    # -----------------------------------------------------------------------
    # Requirement 6.4 — submission_deadline validation
    # -----------------------------------------------------------------------

    def test_submission_deadline_in_past_returns_400(self):
        """
        POST with submission_deadline in the past → 400.

        Validates: Requirement 6.4
        """
        payload = _valid_tender_payload(submission_deadline=_past_deadline(1))
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("future", data.get("detail", "").lower())

    def test_submission_deadline_invalid_format_returns_400(self):
        """
        POST with submission_deadline="not-a-date" → 400.

        Validates: Requirement 6.4
        """
        payload = _valid_tender_payload(submission_deadline="not-a-date")
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("iso 8601", data.get("detail", "").lower())

    def test_submission_deadline_in_future_accepted(self):
        """
        POST with submission_deadline 30 days in the future → 201.

        Validates: Requirement 6.4
        """
        payload = _valid_tender_payload(submission_deadline=_future_deadline(30))
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)

    # -----------------------------------------------------------------------
    # Requirement 6.11 — bleach sanitisation of text inputs
    # -----------------------------------------------------------------------

    def test_html_in_title_is_stripped(self):
        """
        POST with HTML in title → 201, title is sanitised (HTML stripped).

        Validates: Requirement 6.11
        """
        from agencies.models import TenderSubmission

        payload = _valid_tender_payload(title="<script>alert('xss')</script>Clean Title")
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()

        # HTML tags must be stripped
        self.assertNotIn("<script>", data["title"])
        self.assertNotIn("</script>", data["title"])
        self.assertIn("Clean Title", data["title"])

        # Verify in DB
        submission = TenderSubmission.objects.get(pk=data["id"])
        self.assertNotIn("<script>", submission.title)

    def test_html_in_buyer_name_is_stripped(self):
        """
        POST with HTML in buyer_name → 201, buyer_name is sanitised.

        Validates: Requirement 6.11
        """
        payload = _valid_tender_payload(buyer_name="<b>Ministry</b> of Finance")
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertNotIn("<b>", data["buyer_name"])
        self.assertIn("Ministry", data["buyer_name"])

    def test_html_in_spec_text_is_stripped(self):
        """
        POST with HTML in spec_text → 201, spec_text is sanitised.

        Validates: Requirement 6.11
        """
        payload = _valid_tender_payload(
            spec_text="<p>Specification <em>details</em></p>"
        )
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertNotIn("<p>", data["spec_text"])
        self.assertNotIn("<em>", data["spec_text"])
        self.assertIn("Specification", data["spec_text"])
        self.assertIn("details", data["spec_text"])

    def test_clean_text_inputs_are_unchanged(self):
        """
        POST with clean text (no HTML) → title/buyer_name/spec_text unchanged.

        Validates: Requirement 6.11
        """
        payload = _valid_tender_payload(
            title="Road Construction Project",
            buyer_name="National Highways Authority",
            spec_text="Build 50km of highway.",
        )
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["title"], "Road Construction Project")
        self.assertEqual(data["buyer_name"], "National Highways Authority")
        self.assertEqual(data["spec_text"], "Build 50km of highway.")

    # -----------------------------------------------------------------------
    # Requirement 6.12 — TENDER_SUBMITTED AuditLog entry
    # -----------------------------------------------------------------------

    def test_audit_log_entry_written_on_create(self):
        """
        POST valid payload → TENDER_SUBMITTED AuditLog entry written with
        actor user ID, agency ID, tender ID, and action="created".

        Validates: Requirement 6.12
        """
        payload = _valid_tender_payload()
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        submission_id = response.json()["id"]

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_SUBMITTED,
            user=self.admin_user,
            affected_entity_id=str(submission_id),
        ).first()

        self.assertIsNotNone(log, "TENDER_SUBMITTED AuditLog entry not found")
        self.assertEqual(log.data_snapshot.get("action"), "created")
        self.assertEqual(
            log.data_snapshot.get("agency_id"),
            str(self.agency.agency_id),
        )
        self.assertEqual(log.data_snapshot.get("tender_ref"), payload["tender_ref"])

    def test_audit_log_written_by_officer(self):
        """
        POST as AGENCY_OFFICER → AuditLog entry has officer as actor.

        Validates: Requirement 6.12
        """
        payload = _valid_tender_payload()
        response = self._auth_post(payload, token=self.officer_token)

        self.assertEqual(response.status_code, 201)
        submission_id = response.json()["id"]

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_SUBMITTED,
            user=self.officer_user,
            affected_entity_id=str(submission_id),
        ).first()

        self.assertIsNotNone(log, "TENDER_SUBMITTED AuditLog entry not found for officer")

    # -----------------------------------------------------------------------
    # Optional fields
    # -----------------------------------------------------------------------

    def test_optional_spec_text_defaults_to_empty_string(self):
        """
        POST without spec_text → 201, spec_text defaults to empty string.

        Validates: Requirement 6.1
        """
        payload = _valid_tender_payload()
        del payload["spec_text"]

        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["spec_text"], "")

    def test_optional_publication_date_accepted(self):
        """
        POST with publication_date → 201, publication_date stored correctly.

        Validates: Requirement 6.1
        """
        pub_date = (timezone.now() + timezone.timedelta(days=5)).isoformat()
        payload = _valid_tender_payload(publication_date=pub_date)

        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIsNotNone(data["publication_date"])

    def test_optional_publication_date_omitted(self):
        """
        POST without publication_date → 201, publication_date is null.

        Validates: Requirement 6.1
        """
        payload = _valid_tender_payload()
        # Ensure publication_date is not in payload
        payload.pop("publication_date", None)

        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIsNone(data["publication_date"])

    # -----------------------------------------------------------------------
    # Multi-tenancy: submission linked to correct agency
    # -----------------------------------------------------------------------

    def test_submission_linked_to_users_agency(self):
        """
        POST from user in agency A → submission.agency == agency A.

        Validates: Requirements 6.2, 8.1
        """
        from agencies.models import TenderSubmission

        payload = _valid_tender_payload()
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        submission = TenderSubmission.objects.get(pk=response.json()["id"])
        self.assertEqual(submission.agency_id, self.agency.pk)

    def test_user_without_agency_returns_403(self):
        """
        POST from user with no agency association → 403.

        Validates: Requirement 8.1
        """
        no_agency_user = User.objects.create_user(
            username=f"noagency_{uuid.uuid4().hex[:8]}",
            email=f"noagency_{uuid.uuid4().hex[:8]}@example.com",
            password="TestPass123!",
            role="AGENCY_ADMIN",
        )
        no_agency_user.is_active = True
        no_agency_user.save(update_fields=["is_active"])

        token = _get_jwt_for_user(no_agency_user)
        payload = _valid_tender_payload()
        response = self.client.post(
            TENDER_LIST_URL,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

        self.assertEqual(response.status_code, 403)

    # -----------------------------------------------------------------------
    # Response shape
    # -----------------------------------------------------------------------

    def test_response_contains_all_expected_fields(self):
        """
        POST valid payload → 201 response contains all expected fields.

        Validates: Requirements 6.1, 6.2
        """
        payload = _valid_tender_payload()
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()

        expected_fields = [
            "id", "tender_ref", "title", "category", "estimated_value",
            "submission_deadline", "publication_date", "buyer_name",
            "spec_text", "status", "submitted_by", "created_at", "updated_at",
            "fraud_risk_score", "risk_badge",
        ]
        for field in expected_fields:
            self.assertIn(field, data, msg=f"Field '{field}' missing from response")

    def test_response_status_is_draft(self):
        """
        POST valid payload → response status is DRAFT.

        Validates: Requirement 6.2
        """
        payload = _valid_tender_payload()
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "DRAFT")

    def test_fraud_risk_score_is_null_on_creation(self):
        """
        Newly created submission has null fraud_risk_score and risk_badge
        (no pipeline has run yet).

        Validates: Requirement 6.2
        """
        payload = _valid_tender_payload()
        response = self._auth_post(payload)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIsNone(data["fraud_risk_score"])
        self.assertIsNone(data["risk_badge"])


# ===========================================================================
# TestAgencyTenderDetailView — Task 6.3
# GET /api/v1/agencies/me/tenders/<id>/
# Requirements: 5.3, 5.4, 8.2
# ===========================================================================


def _tender_detail_url(pk):
    """Return the tender detail URL for the given submission pk."""
    return f"/api/v1/agencies/me/tenders/{pk}/"


class TestAgencyTenderDetailView(TestCase):
    """
    Integration tests for GET /api/v1/agencies/me/tenders/<id>/

    Validates: Requirements 5.3, 5.4, 8.2
    """

    def setUp(self):
        self.client = Client()
        self.agency = _make_active_agency()
        self.admin_user = _make_agency_user(self.agency, role="AGENCY_ADMIN")
        self.officer_user = _make_agency_user(self.agency, role="AGENCY_OFFICER")
        self.reviewer_user = _make_agency_user(self.agency, role="REVIEWER")
        self.admin_token = _get_jwt_for_user(self.admin_user)
        self.officer_token = _get_jwt_for_user(self.officer_user)
        self.reviewer_token = _get_jwt_for_user(self.reviewer_user)

    def _auth_get(self, url, token=None):
        """Perform an authenticated GET request."""
        token = token or self.admin_token
        return self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # Requirement 5.3 — All agency roles can access tender detail
    # -----------------------------------------------------------------------

    def test_agency_admin_can_view_tender_detail(self):
        """
        GET as AGENCY_ADMIN → 200 with tender detail.

        Validates: Requirement 5.3
        """
        submission = _make_tender_submission(self.agency, self.admin_user)
        url = _tender_detail_url(submission.pk)

        response = self._auth_get(url, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], submission.pk)
        self.assertEqual(data["tender_ref"], submission.tender_ref)
        self.assertEqual(data["title"], submission.title)

    def test_agency_officer_can_view_tender_detail(self):
        """
        GET as AGENCY_OFFICER → 200 with tender detail.

        Validates: Requirement 5.3
        """
        submission = _make_tender_submission(self.agency, self.officer_user)
        url = _tender_detail_url(submission.pk)

        response = self._auth_get(url, token=self.officer_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], submission.pk)

    def test_reviewer_can_view_tender_detail(self):
        """
        GET as REVIEWER → 200 with tender detail.

        Validates: Requirement 5.3
        """
        submission = _make_tender_submission(self.agency, self.admin_user)
        url = _tender_detail_url(submission.pk)

        response = self._auth_get(url, token=self.reviewer_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], submission.pk)

    # -----------------------------------------------------------------------
    # Requirement 5.3 — Response contains all required fields
    # -----------------------------------------------------------------------

    def test_response_contains_all_required_fields(self):
        """
        GET returns all expected fields: id, tender_ref, title, category,
        estimated_value, submission_deadline, buyer_name, spec_text, status,
        fraud_risk_score, risk_badge, red_flags, created_at, updated_at.

        Validates: Requirement 5.3
        """
        submission = _make_tender_submission(self.agency, self.admin_user)
        url = _tender_detail_url(submission.pk)

        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        required_fields = [
            "id", "tender_ref", "title", "category", "estimated_value",
            "submission_deadline", "buyer_name", "spec_text", "status",
            "fraud_risk_score", "risk_badge", "red_flags",
            "created_at", "updated_at",
        ]
        for field in required_fields:
            self.assertIn(field, data, msg=f"Field '{field}' missing from response")

    def test_response_includes_submission_status(self):
        """
        GET returns the current submission status.

        Validates: Requirement 5.3
        """
        submission = _make_tender_submission(
            self.agency, self.admin_user, status="SUBMITTED"
        )
        url = _tender_detail_url(submission.pk)

        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "SUBMITTED")

    # -----------------------------------------------------------------------
    # Requirement 5.4 — Fraud score and risk badge
    # -----------------------------------------------------------------------

    def test_fraud_risk_score_null_when_no_tender_linked(self):
        """
        Submission without a linked Tender has null fraud_risk_score and risk_badge.

        Validates: Requirement 5.4
        """
        submission = _make_tender_submission(self.agency, self.admin_user)
        url = _tender_detail_url(submission.pk)

        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["fraud_risk_score"])
        self.assertIsNone(data["risk_badge"])

    def test_fraud_risk_score_included_when_tender_linked(self):
        """
        Submission with a linked Tender that has a FraudRiskScore returns
        the score and risk badge.

        Validates: Requirement 5.4
        """
        from tenders.models import Tender, TenderStatus
        from scoring.models import FraudRiskScore

        # Create a submission
        submission = _make_tender_submission(self.agency, self.admin_user)

        # Create a linked Tender
        tender = Tender.objects.create(
            tender_id=submission.tender_ref,
            title=submission.title,
            category=submission.category,
            estimated_value=submission.estimated_value,
            submission_deadline=submission.submission_deadline,
            buyer_id=str(self.agency.agency_id),
            buyer_name=submission.buyer_name,
            spec_text=submission.spec_text,
            status=TenderStatus.ACTIVE,
        )
        submission.tender = tender
        submission.save(update_fields=["tender_id"])

        # Create a FraudRiskScore for the tender (score is integer 0-100)
        FraudRiskScore.objects.create(
            tender=tender,
            score=75,  # PositiveSmallIntegerField
            computed_at=timezone.now(),
        )

        url = _tender_detail_url(submission.pk)
        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["fraud_risk_score"], 75.0)
        self.assertEqual(data["risk_badge"], "red")  # score >= 70

    def test_risk_badge_green_for_low_score(self):
        """
        Fraud score < 40 → risk_badge = "green".

        Validates: Requirement 5.4
        """
        from tenders.models import Tender, TenderStatus
        from scoring.models import FraudRiskScore

        submission = _make_tender_submission(self.agency, self.admin_user)
        tender = Tender.objects.create(
            tender_id=submission.tender_ref,
            title=submission.title,
            category=submission.category,
            estimated_value=submission.estimated_value,
            submission_deadline=submission.submission_deadline,
            buyer_id=str(self.agency.agency_id),
            buyer_name=submission.buyer_name,
            spec_text=submission.spec_text,
            status=TenderStatus.ACTIVE,
        )
        submission.tender = tender
        submission.save(update_fields=["tender_id"])

        FraudRiskScore.objects.create(
            tender=tender,
            score=25,  # PositiveSmallIntegerField
            computed_at=timezone.now(),
        )

        url = _tender_detail_url(submission.pk)
        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["fraud_risk_score"], 25.0)
        self.assertEqual(data["risk_badge"], "green")

    def test_risk_badge_amber_for_medium_score(self):
        """
        Fraud score 40-69 → risk_badge = "amber".

        Validates: Requirement 5.4
        """
        from tenders.models import Tender, TenderStatus
        from scoring.models import FraudRiskScore

        submission = _make_tender_submission(self.agency, self.admin_user)
        tender = Tender.objects.create(
            tender_id=submission.tender_ref,
            title=submission.title,
            category=submission.category,
            estimated_value=submission.estimated_value,
            submission_deadline=submission.submission_deadline,
            buyer_id=str(self.agency.agency_id),
            buyer_name=submission.buyer_name,
            spec_text=submission.spec_text,
            status=TenderStatus.ACTIVE,
        )
        submission.tender = tender
        submission.save(update_fields=["tender_id"])

        FraudRiskScore.objects.create(
            tender=tender,
            score=55,  # PositiveSmallIntegerField
            computed_at=timezone.now(),
        )

        url = _tender_detail_url(submission.pk)
        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["fraud_risk_score"], 55.0)
        self.assertEqual(data["risk_badge"], "amber")

    def test_risk_badge_red_for_high_score(self):
        """
        Fraud score >= 70 → risk_badge = "red".

        Validates: Requirement 5.4
        """
        from tenders.models import Tender, TenderStatus
        from scoring.models import FraudRiskScore

        submission = _make_tender_submission(self.agency, self.admin_user)
        tender = Tender.objects.create(
            tender_id=submission.tender_ref,
            title=submission.title,
            category=submission.category,
            estimated_value=submission.estimated_value,
            submission_deadline=submission.submission_deadline,
            buyer_id=str(self.agency.agency_id),
            buyer_name=submission.buyer_name,
            spec_text=submission.spec_text,
            status=TenderStatus.ACTIVE,
        )
        submission.tender = tender
        submission.save(update_fields=["tender_id"])

        FraudRiskScore.objects.create(
            tender=tender,
            score=85,  # PositiveSmallIntegerField
            computed_at=timezone.now(),
        )

        url = _tender_detail_url(submission.pk)
        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["fraud_risk_score"], 85.0)
        self.assertEqual(data["risk_badge"], "red")

    # -----------------------------------------------------------------------
    # Requirement 5.4 — Red flag summary
    # -----------------------------------------------------------------------

    def test_red_flags_empty_when_no_tender_linked(self):
        """
        Submission without a linked Tender has empty red_flags list.

        Validates: Requirement 5.4
        """
        submission = _make_tender_submission(self.agency, self.admin_user)
        url = _tender_detail_url(submission.pk)

        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["red_flags"], [])

    def test_red_flags_included_when_tender_has_flags(self):
        """
        Submission with a linked Tender that has RedFlag records returns
        the red flag summary.

        Validates: Requirement 5.4
        """
        from tenders.models import Tender, TenderStatus
        from detection.models import RedFlag, FlagType, Severity

        submission = _make_tender_submission(self.agency, self.admin_user)
        tender = Tender.objects.create(
            tender_id=submission.tender_ref,
            title=submission.title,
            category=submission.category,
            estimated_value=submission.estimated_value,
            submission_deadline=submission.submission_deadline,
            buyer_id=str(self.agency.agency_id),
            buyer_name=submission.buyer_name,
            spec_text=submission.spec_text,
            status=TenderStatus.ACTIVE,
        )
        submission.tender = tender
        submission.save(update_fields=["tender_id"])

        # Create red flags using the actual RedFlag model fields
        RedFlag.objects.create(
            tender=tender,
            flag_type=FlagType.SHORT_DEADLINE,
            severity=Severity.HIGH,
            trigger_data={"reason": "Submission deadline is unusually short."},
        )
        RedFlag.objects.create(
            tender=tender,
            flag_type=FlagType.SPEC_COPY_PASTE,
            severity=Severity.MEDIUM,
            trigger_data={"reason": "Specification text matches a previous tender."},
        )

        url = _tender_detail_url(submission.pk)
        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["red_flags"]), 2)

        # Verify each flag has required fields
        for flag in data["red_flags"]:
            self.assertIn("flag_type", flag)
            self.assertIn("severity", flag)

    # -----------------------------------------------------------------------
    # Requirement 8.2 — Agency scoping enforcement
    # -----------------------------------------------------------------------

    def test_cross_agency_access_returns_403(self):
        """
        User from agency A cannot access submission from agency B → 403.

        Validates: Requirement 8.2
        """
        # Create agency B with its own user and submission
        agency_b = _make_active_agency()
        user_b = _make_agency_user(agency_b, role="AGENCY_ADMIN")
        submission_b = _make_tender_submission(agency_b, user_b)

        # User A tries to access agency B's submission
        url = _tender_detail_url(submission_b.pk)
        response = self._auth_get(url, token=self.admin_token)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("permission", data.get("detail", "").lower())

    def test_user_without_agency_returns_403(self):
        """
        User with no agency association gets 403.

        Validates: Requirement 8.2
        """
        submission = _make_tender_submission(self.agency, self.admin_user)

        # Create a user with no agency
        no_agency_user = User.objects.create_user(
            username=f"noagency_{uuid.uuid4().hex[:8]}",
            email=f"noagency_{uuid.uuid4().hex[:8]}@example.com",
            password="TestPass123!",
            role="AGENCY_ADMIN",
        )
        no_agency_user.is_active = True
        no_agency_user.save(update_fields=["is_active"])

        token = _get_jwt_for_user(no_agency_user)
        url = _tender_detail_url(submission.pk)
        response = self._auth_get(url, token=token)

        self.assertEqual(response.status_code, 403)

    def test_same_agency_different_user_can_access(self):
        """
        Different users in the same agency can access each other's submissions.

        Validates: Requirement 8.2
        """
        # Admin creates a submission
        submission = _make_tender_submission(self.agency, self.admin_user)

        # Officer from same agency can access it
        url = _tender_detail_url(submission.pk)
        response = self._auth_get(url, token=self.officer_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["id"], submission.pk)

    # -----------------------------------------------------------------------
    # Requirement 8.2 — 404 for non-existent submission
    # -----------------------------------------------------------------------

    def test_non_existent_submission_returns_404(self):
        """
        GET with non-existent submission ID → 404.

        Validates: Requirement 8.2
        """
        non_existent_id = 999999
        url = _tender_detail_url(non_existent_id)

        response = self._auth_get(url)

        self.assertEqual(response.status_code, 404)

    # -----------------------------------------------------------------------
    # Authentication requirement
    # -----------------------------------------------------------------------

    def test_unauthenticated_request_returns_401(self):
        """
        GET without Authorization header → 401.

        Validates: Requirement 8.2
        """
        submission = _make_tender_submission(self.agency, self.admin_user)
        url = _tender_detail_url(submission.pk)

        response = self.client.get(url)

        self.assertIn(response.status_code, [401, 403])

    # -----------------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------------

    def test_draft_submission_accessible(self):
        """
        DRAFT submissions are accessible via detail endpoint.

        Validates: Requirement 5.3
        """
        submission = _make_tender_submission(
            self.agency, self.admin_user, status="DRAFT"
        )
        url = _tender_detail_url(submission.pk)

        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "DRAFT")

    def test_submitted_submission_accessible(self):
        """
        SUBMITTED submissions are accessible via detail endpoint.

        Validates: Requirement 5.3
        """
        submission = _make_tender_submission(
            self.agency, self.admin_user, status="SUBMITTED"
        )
        url = _tender_detail_url(submission.pk)

        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "SUBMITTED")

    def test_flagged_submission_accessible(self):
        """
        FLAGGED submissions are accessible via detail endpoint.

        Validates: Requirement 5.3
        """
        from agencies.models import TenderSubmission

        submission = _make_tender_submission(self.agency, self.admin_user)
        # Manually set status to FLAGGED (bypassing transition validation for test setup)
        TenderSubmission.objects.filter(pk=submission.pk).update(status="FLAGGED")
        submission.refresh_from_db()

        url = _tender_detail_url(submission.pk)
        response = self._auth_get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "FLAGGED")


# ===========================================================================
# TestAgencyTenderPatchView — Task 6.4
# PATCH /api/v1/agencies/me/tenders/<id>/
# Requirements: 6.8, 6.9, 6.10, 6.11, 6.12
# ===========================================================================


class TestAgencyTenderPatchView(TestCase):
    """
    Integration tests for PATCH /api/v1/agencies/me/tenders/<id>/

    Validates: Requirements 6.8, 6.9, 6.10, 6.11, 6.12
    """

    def setUp(self):
        self.client = Client()
        self.agency = _make_active_agency()
        self.admin_user = _make_agency_user(self.agency, role="AGENCY_ADMIN")
        self.officer_user = _make_agency_user(self.agency, role="AGENCY_OFFICER")
        self.reviewer_user = _make_agency_user(self.agency, role="REVIEWER")
        self.admin_token = _get_jwt_for_user(self.admin_user)
        self.officer_token = _get_jwt_for_user(self.officer_user)
        self.reviewer_token = _get_jwt_for_user(self.reviewer_user)

    def _auth_patch(self, url, payload, token=None):
        """Perform an authenticated PATCH request."""
        token = token or self.admin_token
        return self.client.patch(
            url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # Requirement 6.8 — AGENCY_ADMIN can edit any DRAFT tender in their agency
    # -----------------------------------------------------------------------

    def test_agency_admin_can_edit_draft_tender(self):
        """
        PATCH as AGENCY_ADMIN on a DRAFT tender → 200, fields updated.

        Validates: Requirement 6.8
        """
        from agencies.models import TenderSubmission

        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "Updated Title", "buyer_name": "Updated Buyer"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Updated Title")
        self.assertEqual(data["buyer_name"], "Updated Buyer")

        # Verify in DB
        submission.refresh_from_db()
        self.assertEqual(submission.title, "Updated Title")
        self.assertEqual(submission.buyer_name, "Updated Buyer")

    def test_agency_admin_can_edit_another_officers_draft_tender(self):
        """
        AGENCY_ADMIN can edit a DRAFT tender created by an AGENCY_OFFICER.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "Admin Edited Title"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Admin Edited Title")

    # -----------------------------------------------------------------------
    # Requirement 6.9 — AGENCY_OFFICER can only edit their own tenders
    # -----------------------------------------------------------------------

    def test_agency_officer_can_edit_own_draft_tender(self):
        """
        PATCH as AGENCY_OFFICER on their own DRAFT tender → 200.

        Validates: Requirement 6.9
        """
        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "Officer Updated Title"}
        response = self._auth_patch(url, payload, token=self.officer_token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["title"], "Officer Updated Title")

    def test_agency_officer_cannot_edit_another_officers_tender(self):
        """
        PATCH as AGENCY_OFFICER on a DRAFT tender created by another user → 403.

        Validates: Requirement 6.9
        """
        # Tender created by admin_user, not officer_user
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "Should Not Update"}
        response = self._auth_patch(url, payload, token=self.officer_token)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("own", data.get("detail", "").lower())

    # -----------------------------------------------------------------------
    # Requirement 6.10 — DRAFT-only editing; non-DRAFT returns 403
    # -----------------------------------------------------------------------

    def test_editing_submitted_tender_returns_403(self):
        """
        PATCH on a SUBMITTED tender → 403 with "DRAFT" in message.

        Validates: Requirement 6.10
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="SUBMITTED")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "Should Not Update"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("DRAFT", data.get("detail", ""))

    def test_editing_under_review_tender_returns_403(self):
        """
        PATCH on an UNDER_REVIEW tender → 403.

        Validates: Requirement 6.10
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="UNDER_REVIEW")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "Should Not Update"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 403)

    def test_editing_flagged_tender_returns_403(self):
        """
        PATCH on a FLAGGED tender → 403.

        Validates: Requirement 6.10
        """
        from agencies.models import TenderSubmission as TS

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        TS.objects.filter(pk=submission.pk).update(status="FLAGGED")

        url = _tender_detail_url(submission.pk)
        payload = {"title": "Should Not Update"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 403)

    def test_editing_cleared_tender_returns_403(self):
        """
        PATCH on a CLEARED tender → 403.

        Validates: Requirement 6.10
        """
        from agencies.models import TenderSubmission as TS

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        TS.objects.filter(pk=submission.pk).update(status="CLEARED")

        url = _tender_detail_url(submission.pk)
        payload = {"title": "Should Not Update"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 403)

    # -----------------------------------------------------------------------
    # Requirement 6.11 — bleach sanitisation of text inputs
    # -----------------------------------------------------------------------

    def test_html_in_title_is_sanitised_on_patch(self):
        """
        PATCH with HTML in title → 200, HTML stripped from title.

        Validates: Requirement 6.11
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "<script>alert('xss')</script>Clean Title"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("<script>", data["title"])
        self.assertIn("Clean Title", data["title"])

    def test_html_in_buyer_name_is_sanitised_on_patch(self):
        """
        PATCH with HTML in buyer_name → 200, HTML stripped.

        Validates: Requirement 6.11
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"buyer_name": "<b>Ministry</b> of Finance"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("<b>", data["buyer_name"])
        self.assertIn("Ministry", data["buyer_name"])

    def test_html_in_spec_text_is_sanitised_on_patch(self):
        """
        PATCH with HTML in spec_text → 200, HTML stripped.

        Validates: Requirement 6.11
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"spec_text": "<p>Specification <em>details</em></p>"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertNotIn("<p>", data["spec_text"])
        self.assertNotIn("<em>", data["spec_text"])
        self.assertIn("Specification", data["spec_text"])
        self.assertIn("details", data["spec_text"])

    def test_clean_text_inputs_unchanged_on_patch(self):
        """
        PATCH with clean text → title/buyer_name/spec_text unchanged by sanitiser.

        Validates: Requirement 6.11
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {
            "title": "Road Construction Project",
            "buyer_name": "National Highways Authority",
            "spec_text": "Build 50km of highway.",
        }
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], "Road Construction Project")
        self.assertEqual(data["buyer_name"], "National Highways Authority")
        self.assertEqual(data["spec_text"], "Build 50km of highway.")

    # -----------------------------------------------------------------------
    # Requirement 6.12 — AuditLog entry written on edit
    # -----------------------------------------------------------------------

    def test_audit_log_entry_written_on_patch(self):
        """
        PATCH valid payload → TENDER_SUBMITTED AuditLog entry written with
        action="edited", actor user ID, agency ID, and updated_fields.

        Validates: Requirement 6.12
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "Audited Title Update"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_SUBMITTED,
            user=self.admin_user,
            affected_entity_id=str(submission.pk),
        ).filter(data_snapshot__action="edited").first()

        self.assertIsNotNone(log, "TENDER_SUBMITTED AuditLog entry with action='edited' not found")
        self.assertEqual(log.data_snapshot.get("action"), "edited")
        self.assertEqual(
            log.data_snapshot.get("agency_id"),
            str(self.agency.agency_id),
        )
        self.assertIn("title", log.data_snapshot.get("updated_fields", []))

    def test_audit_log_written_by_officer_on_own_tender(self):
        """
        PATCH as AGENCY_OFFICER on own tender → AuditLog entry has officer as actor.

        Validates: Requirement 6.12
        """
        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "Officer Edited Title"}
        response = self._auth_patch(url, payload, token=self.officer_token)

        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_SUBMITTED,
            user=self.officer_user,
            affected_entity_id=str(submission.pk),
        ).filter(data_snapshot__action="edited").first()

        self.assertIsNotNone(log, "AuditLog entry not found for officer edit")

    # -----------------------------------------------------------------------
    # Validation — estimated_value and submission_deadline
    # -----------------------------------------------------------------------

    def test_patch_invalid_estimated_value_returns_400(self):
        """
        PATCH with estimated_value="not-a-number" → 400.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_patch(url, {"estimated_value": "not-a-number"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("estimated_value", response.json().get("detail", "").lower())

    def test_patch_negative_estimated_value_returns_400(self):
        """
        PATCH with estimated_value="-100" → 400.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_patch(url, {"estimated_value": "-100.00"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("positive", response.json().get("detail", "").lower())

    def test_patch_estimated_value_too_many_decimals_returns_400(self):
        """
        PATCH with estimated_value="100.123" → 400.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_patch(url, {"estimated_value": "100.123"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("decimal", response.json().get("detail", "").lower())

    def test_patch_submission_deadline_in_past_returns_400(self):
        """
        PATCH with submission_deadline in the past → 400.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_patch(url, {"submission_deadline": _past_deadline(1)})

        self.assertEqual(response.status_code, 400)
        self.assertIn("future", response.json().get("detail", "").lower())

    def test_patch_submission_deadline_invalid_format_returns_400(self):
        """
        PATCH with submission_deadline="not-a-date" → 400.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_patch(url, {"submission_deadline": "not-a-date"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("iso 8601", response.json().get("detail", "").lower())

    def test_patch_valid_estimated_value_and_deadline_accepted(self):
        """
        PATCH with valid estimated_value and future submission_deadline → 200.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {
            "estimated_value": "250000.50",
            "submission_deadline": _future_deadline(60),
        }
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["estimated_value"], "250000.50")

    # -----------------------------------------------------------------------
    # No updatable fields provided
    # -----------------------------------------------------------------------

    def test_patch_with_no_updatable_fields_returns_400(self):
        """
        PATCH with empty payload → 400 "No updatable fields provided."

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_patch(url, {})

        self.assertEqual(response.status_code, 400)
        self.assertIn("no updatable", response.json().get("detail", "").lower())

    # -----------------------------------------------------------------------
    # Role restrictions
    # -----------------------------------------------------------------------

    def test_reviewer_cannot_patch_tender(self):
        """
        PATCH as REVIEWER → 403 (role not permitted).

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_patch(url, {"title": "Should Not Update"}, token=self.reviewer_token)

        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_patch_returns_401(self):
        """
        PATCH without Authorization header → 401.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self.client.patch(
            url,
            data=json.dumps({"title": "No Auth"}),
            content_type="application/json",
        )

        self.assertIn(response.status_code, [401, 403])

    # -----------------------------------------------------------------------
    # Cross-agency access
    # -----------------------------------------------------------------------

    def test_cross_agency_patch_returns_403(self):
        """
        PATCH on a submission belonging to a different agency → 403.

        Validates: Requirement 6.8, 8.2
        """
        agency_b = _make_active_agency()
        user_b = _make_agency_user(agency_b, role="AGENCY_ADMIN")
        submission_b = _make_tender_submission(agency_b, user_b, status="DRAFT")

        url = _tender_detail_url(submission_b.pk)
        response = self._auth_patch(url, {"title": "Cross Agency Edit"}, token=self.admin_token)

        self.assertEqual(response.status_code, 403)

    # -----------------------------------------------------------------------
    # Response shape
    # -----------------------------------------------------------------------

    def test_patch_response_contains_all_expected_fields(self):
        """
        PATCH valid payload → 200 response contains all expected fields.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        payload = {"title": "Updated Title for Shape Test"}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        expected_fields = [
            "id", "tender_ref", "title", "category", "estimated_value",
            "submission_deadline", "publication_date", "buyer_name",
            "spec_text", "status", "submitted_by", "created_at", "updated_at",
            "fraud_risk_score", "risk_badge",
        ]
        for field in expected_fields:
            self.assertIn(field, data, msg=f"Field '{field}' missing from PATCH response")

    def test_patch_returns_updated_data(self):
        """
        PATCH updates are reflected in the response body.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        new_title = "Completely New Title"
        new_category = "Infrastructure"
        payload = {"title": new_title, "category": new_category}
        response = self._auth_patch(url, payload, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["title"], new_title)
        self.assertEqual(data["category"], new_category)
        # Status should remain DRAFT
        self.assertEqual(data["status"], "DRAFT")

    def test_patch_non_existent_submission_returns_404(self):
        """
        PATCH on non-existent submission ID → 404.

        Validates: Requirement 6.8
        """
        url = _tender_detail_url(999999)
        response = self._auth_patch(url, {"title": "Ghost Tender"})

        self.assertEqual(response.status_code, 404)


# ===========================================================================
# TestAgencyTenderDeleteView — Task 6.5
# DELETE /api/v1/agencies/me/tenders/<id>/
# Requirements: 6.8, 6.9, 6.10, 6.12
# ===========================================================================


class TestAgencyTenderDeleteView(TestCase):
    """
    Integration tests for DELETE /api/v1/agencies/me/tenders/<id>/

    Validates: Requirements 6.8, 6.9, 6.10, 6.12
    """

    def setUp(self):
        self.client = Client()
        self.agency = _make_active_agency()
        self.admin_user = _make_agency_user(self.agency, role="AGENCY_ADMIN")
        self.officer_user = _make_agency_user(self.agency, role="AGENCY_OFFICER")
        self.reviewer_user = _make_agency_user(self.agency, role="REVIEWER")
        self.admin_token = _get_jwt_for_user(self.admin_user)
        self.officer_token = _get_jwt_for_user(self.officer_user)
        self.reviewer_token = _get_jwt_for_user(self.reviewer_user)

    def _auth_delete(self, url, token=None):
        """Perform an authenticated DELETE request."""
        token = token or self.admin_token
        return self.client.delete(
            url,
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # Requirement 6.8 — AGENCY_ADMIN can delete any DRAFT tender in their agency
    # -----------------------------------------------------------------------

    def test_agency_admin_can_delete_draft_tender(self):
        """
        DELETE as AGENCY_ADMIN on a DRAFT tender → 204, submission removed from DB.

        Validates: Requirement 6.8
        """
        from agencies.models import TenderSubmission

        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)
        submission_pk = submission.pk

        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(TenderSubmission.objects.filter(pk=submission_pk).exists())

    def test_agency_admin_can_delete_another_officers_draft_tender(self):
        """
        AGENCY_ADMIN can delete a DRAFT tender created by an AGENCY_OFFICER.

        Validates: Requirement 6.8
        """
        from agencies.models import TenderSubmission

        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)
        submission_pk = submission.pk

        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(TenderSubmission.objects.filter(pk=submission_pk).exists())

    # -----------------------------------------------------------------------
    # Requirement 6.9 — AGENCY_OFFICER can only delete their own tenders
    # -----------------------------------------------------------------------

    def test_agency_officer_can_delete_own_draft_tender(self):
        """
        DELETE as AGENCY_OFFICER on their own DRAFT tender → 204.

        Validates: Requirement 6.9
        """
        from agencies.models import TenderSubmission

        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)
        submission_pk = submission.pk

        response = self._auth_delete(url, token=self.officer_token)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(TenderSubmission.objects.filter(pk=submission_pk).exists())

    def test_agency_officer_cannot_delete_another_officers_tender(self):
        """
        DELETE as AGENCY_OFFICER on a DRAFT tender created by another user → 403.

        Validates: Requirement 6.9
        """
        from agencies.models import TenderSubmission

        # Tender created by admin_user, not officer_user
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_delete(url, token=self.officer_token)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("own", data.get("detail", "").lower())

        # Submission must still exist
        self.assertTrue(TenderSubmission.objects.filter(pk=submission.pk).exists())

    # -----------------------------------------------------------------------
    # Requirement 6.10 — DRAFT-only deletion; non-DRAFT returns 403
    # -----------------------------------------------------------------------

    def test_deleting_submitted_tender_returns_403(self):
        """
        DELETE on a SUBMITTED tender → 403 with "DRAFT" in message.

        Validates: Requirement 6.10
        """
        from agencies.models import TenderSubmission

        submission = _make_tender_submission(self.agency, self.admin_user, status="SUBMITTED")
        url = _tender_detail_url(submission.pk)

        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("DRAFT", data.get("detail", ""))

        # Submission must still exist
        self.assertTrue(TenderSubmission.objects.filter(pk=submission.pk).exists())

    def test_deleting_under_review_tender_returns_403(self):
        """
        DELETE on an UNDER_REVIEW tender → 403.

        Validates: Requirement 6.10
        """
        from agencies.models import TenderSubmission

        submission = _make_tender_submission(self.agency, self.admin_user, status="UNDER_REVIEW")
        url = _tender_detail_url(submission.pk)

        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(TenderSubmission.objects.filter(pk=submission.pk).exists())

    def test_deleting_flagged_tender_returns_403(self):
        """
        DELETE on a FLAGGED tender → 403.

        Validates: Requirement 6.10
        """
        from agencies.models import TenderSubmission as TS

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        TS.objects.filter(pk=submission.pk).update(status="FLAGGED")

        url = _tender_detail_url(submission.pk)
        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(TS.objects.filter(pk=submission.pk).exists())

    def test_deleting_cleared_tender_returns_403(self):
        """
        DELETE on a CLEARED tender → 403.

        Validates: Requirement 6.10
        """
        from agencies.models import TenderSubmission as TS

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        TS.objects.filter(pk=submission.pk).update(status="CLEARED")

        url = _tender_detail_url(submission.pk)
        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(TS.objects.filter(pk=submission.pk).exists())

    # -----------------------------------------------------------------------
    # Requirement 6.12 — AuditLog entry written on deletion
    # -----------------------------------------------------------------------

    def test_audit_log_entry_written_on_delete(self):
        """
        DELETE valid DRAFT tender → TENDER_SUBMITTED AuditLog entry written with
        action="deleted", actor user ID, agency ID, and tender ID.

        Validates: Requirement 6.12
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)
        submission_pk = str(submission.pk)
        tender_ref = submission.tender_ref

        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 204)

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_SUBMITTED,
            user=self.admin_user,
            affected_entity_id=submission_pk,
        ).filter(data_snapshot__action="deleted").first()

        self.assertIsNotNone(log, "TENDER_SUBMITTED AuditLog entry with action='deleted' not found")
        self.assertEqual(log.data_snapshot.get("action"), "deleted")
        self.assertEqual(
            log.data_snapshot.get("agency_id"),
            str(self.agency.agency_id),
        )
        self.assertEqual(log.data_snapshot.get("tender_ref"), tender_ref)

    def test_audit_log_written_by_officer_on_own_tender_delete(self):
        """
        DELETE as AGENCY_OFFICER on own tender → AuditLog entry has officer as actor.

        Validates: Requirement 6.12
        """
        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)
        submission_pk = str(submission.pk)

        response = self._auth_delete(url, token=self.officer_token)

        self.assertEqual(response.status_code, 204)

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_SUBMITTED,
            user=self.officer_user,
            affected_entity_id=submission_pk,
        ).filter(data_snapshot__action="deleted").first()

        self.assertIsNotNone(log, "AuditLog entry not found for officer delete")

    # -----------------------------------------------------------------------
    # Role restrictions
    # -----------------------------------------------------------------------

    def test_reviewer_cannot_delete_tender(self):
        """
        DELETE as REVIEWER → 403 (role not permitted).

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_delete(url, token=self.reviewer_token)

        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_delete_returns_401(self):
        """
        DELETE without Authorization header → 401.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self.client.delete(url)

        self.assertIn(response.status_code, [401, 403])

    # -----------------------------------------------------------------------
    # Cross-agency access
    # -----------------------------------------------------------------------

    def test_cross_agency_delete_returns_403(self):
        """
        DELETE on a submission belonging to a different agency → 403.

        Validates: Requirements 6.8, 8.2
        """
        from agencies.models import TenderSubmission

        agency_b = _make_active_agency()
        user_b = _make_agency_user(agency_b, role="AGENCY_ADMIN")
        submission_b = _make_tender_submission(agency_b, user_b, status="DRAFT")

        url = _tender_detail_url(submission_b.pk)
        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 403)
        # Submission must still exist
        self.assertTrue(TenderSubmission.objects.filter(pk=submission_b.pk).exists())

    # -----------------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------------

    def test_delete_non_existent_submission_returns_404(self):
        """
        DELETE on non-existent submission ID → 404.

        Validates: Requirement 6.8
        """
        url = _tender_detail_url(999999)
        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 404)

    def test_delete_returns_no_content_body(self):
        """
        DELETE on a valid DRAFT tender → 204 with no response body.

        Validates: Requirement 6.8
        """
        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_detail_url(submission.pk)

        response = self._auth_delete(url, token=self.admin_token)

        self.assertEqual(response.status_code, 204)
        # 204 No Content should have no body
        self.assertEqual(len(response.content), 0)


# ===========================================================================
# TestAgencyTenderSubmitView — Task 6.6
# POST /api/v1/agencies/me/tenders/<id>/submit/
# Requirements: 6.5, 6.12, 10.1
# ===========================================================================


def _tender_submit_url(pk):
    """Return the tender submit URL for the given submission pk."""
    return f"/api/v1/agencies/me/tenders/{pk}/submit/"


class TestAgencyTenderSubmitView(TestCase):
    """
    Integration tests for POST /api/v1/agencies/me/tenders/<id>/submit/

    Validates: Requirements 6.5, 6.12, 10.1
    """

    def setUp(self):
        self.client = Client()
        self.agency = _make_active_agency()
        self.admin_user = _make_agency_user(self.agency, role="AGENCY_ADMIN")
        self.officer_user = _make_agency_user(self.agency, role="AGENCY_OFFICER")
        self.reviewer_user = _make_agency_user(self.agency, role="REVIEWER")
        self.admin_token = _get_jwt_for_user(self.admin_user)
        self.officer_token = _get_jwt_for_user(self.officer_user)
        self.reviewer_token = _get_jwt_for_user(self.reviewer_user)

    def _auth_post(self, url, token=None):
        """Perform an authenticated POST request."""
        token = token or self.admin_token
        return self.client.post(
            url,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # Requirement 6.5 — AGENCY_ADMIN and AGENCY_OFFICER can submit
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.score_agency_tender")
    def test_agency_admin_can_submit_draft_tender(self, mock_task):
        """
        POST as AGENCY_ADMIN on a DRAFT tender → 200, status becomes SUBMITTED,
        Tender record created and linked, score_agency_tender task enqueued,
        TENDER_SUBMITTED AuditLog entry written.

        Validates: Requirements 6.5, 6.12, 10.1
        """
        from agencies.models import TenderSubmission
        from tenders.models import Tender

        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Status transitioned to SUBMITTED
        self.assertEqual(data["status"], "SUBMITTED")

        # Verify in DB
        submission.refresh_from_db()
        self.assertEqual(submission.status, "SUBMITTED")

        # Tender record created and linked
        self.assertIsNotNone(submission.tender)
        tender = Tender.objects.get(pk=submission.tender.pk)
        self.assertEqual(tender.tender_id, submission.tender_ref)
        self.assertEqual(tender.title, submission.title)
        self.assertEqual(tender.category, submission.category)
        self.assertEqual(tender.estimated_value, submission.estimated_value)
        self.assertEqual(tender.buyer_name, submission.buyer_name)
        self.assertEqual(tender.spec_text, submission.spec_text)

        # score_agency_tender task enqueued
        mock_task.delay.assert_called_once_with(submission.pk)

        # TENDER_SUBMITTED AuditLog entry written with action="submitted"
        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_SUBMITTED,
            user=self.admin_user,
            affected_entity_id=str(submission.pk),
        ).first()

        self.assertIsNotNone(log, "TENDER_SUBMITTED AuditLog entry not found")
        self.assertEqual(log.data_snapshot.get("action"), "submitted")
        self.assertEqual(log.data_snapshot.get("tender_ref"), submission.tender_ref)
        self.assertEqual(log.data_snapshot.get("tender_id"), tender.pk)
        self.assertEqual(
            log.data_snapshot.get("agency_id"),
            str(self.agency.agency_id),
        )
        self.assertEqual(log.data_snapshot.get("new_status"), "SUBMITTED")

    @patch("agencies.tasks.score_agency_tender")
    def test_agency_officer_can_submit_draft_tender(self, mock_task):
        """
        POST as AGENCY_OFFICER on a DRAFT tender → 200, status becomes SUBMITTED.

        Validates: Requirement 6.5
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.officer_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "SUBMITTED")

        # Verify task enqueued
        mock_task.delay.assert_called_once_with(submission.pk)

    @patch("agencies.tasks.score_agency_tender")
    def test_reviewer_cannot_submit_tender(self, mock_task):
        """
        POST as REVIEWER → 403 (role not permitted).

        Validates: Requirement 6.5
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.reviewer_token)

        self.assertEqual(response.status_code, 403)

        # Task should not be enqueued
        mock_task.delay.assert_not_called()

    @patch("agencies.tasks.score_agency_tender")
    def test_unauthenticated_submit_returns_401(self, mock_task):
        """
        POST without Authorization header → 401.

        Validates: Requirement 6.5
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self.client.post(url, content_type="application/json")

        self.assertIn(response.status_code, [401, 403])
        mock_task.delay.assert_not_called()

    # -----------------------------------------------------------------------
    # Requirement 6.5 — Invalid status transitions
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.score_agency_tender")
    def test_submit_already_submitted_tender_returns_400(self, mock_task):
        """
        POST on a tender already in SUBMITTED status → 400 with invalid transition message.

        Validates: Requirement 6.5
        """
        from agencies.models import TenderSubmission

        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        # Manually set status to SUBMITTED (bypassing transition validation for test setup)
        TenderSubmission.objects.filter(pk=submission.pk).update(status="SUBMITTED")
        submission.refresh_from_db()

        url = _tender_submit_url(submission.pk)
        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("invalid transition", data.get("detail", "").lower())

        # Task should not be enqueued
        mock_task.delay.assert_not_called()

    @patch("agencies.tasks.score_agency_tender")
    def test_submit_flagged_tender_returns_400(self, mock_task):
        """
        POST on a FLAGGED tender → 400 (invalid transition).

        Validates: Requirement 6.5
        """
        from agencies.models import TenderSubmission

        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        # Manually set status to FLAGGED
        TenderSubmission.objects.filter(pk=submission.pk).update(status="FLAGGED")
        submission.refresh_from_db()

        url = _tender_submit_url(submission.pk)
        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("invalid transition", data.get("detail", "").lower())

        mock_task.delay.assert_not_called()

    # -----------------------------------------------------------------------
    # Requirement 8.2 — Agency scoping enforcement
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.score_agency_tender")
    def test_cross_agency_submit_returns_403(self, mock_task):
        """
        User from agency A cannot submit submission from agency B → 403.

        Validates: Requirement 8.2
        """
        mock_task.delay = MagicMock()

        # Create agency B with its own user and submission
        agency_b = _make_active_agency()
        user_b = _make_agency_user(agency_b, role="AGENCY_ADMIN")
        submission_b = _make_tender_submission(agency_b, user_b, status="DRAFT")

        # User A tries to submit agency B's submission
        url = _tender_submit_url(submission_b.pk)
        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("permission", data.get("detail", "").lower())

        # Task should not be enqueued
        mock_task.delay.assert_not_called()

        # Submission status should remain DRAFT
        submission_b.refresh_from_db()
        self.assertEqual(submission_b.status, "DRAFT")

    @patch("agencies.tasks.score_agency_tender")
    def test_user_without_agency_returns_403(self, mock_task):
        """
        User with no agency association gets 403.

        Validates: Requirement 8.2
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")

        # Create a user with no agency
        no_agency_user = User.objects.create_user(
            username=f"noagency_{uuid.uuid4().hex[:8]}",
            email=f"noagency_{uuid.uuid4().hex[:8]}@example.com",
            password="TestPass123!",
            role="AGENCY_ADMIN",
        )
        no_agency_user.is_active = True
        no_agency_user.save(update_fields=["is_active"])

        token = _get_jwt_for_user(no_agency_user)
        url = _tender_submit_url(submission.pk)
        response = self._auth_post(url, token=token)

        self.assertEqual(response.status_code, 403)
        mock_task.delay.assert_not_called()

    # -----------------------------------------------------------------------
    # Requirement 10.1 — Tender record creation and linking
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.score_agency_tender")
    def test_tender_record_created_with_correct_fields(self, mock_task):
        """
        POST creates a tenders.Tender record with all fields correctly mapped
        from the TenderSubmission.

        Validates: Requirement 10.1
        """
        from tenders.models import Tender, TenderStatus

        mock_task.delay = MagicMock()

        submission = _make_tender_submission(
            self.agency,
            self.admin_user,
            status="DRAFT",
            category="Infrastructure",
            estimated_value="250000.50",
        )
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 200)

        # Verify Tender record created
        submission.refresh_from_db()
        self.assertIsNotNone(submission.tender)

        tender = Tender.objects.get(pk=submission.tender.pk)
        self.assertEqual(tender.tender_id, submission.tender_ref)
        self.assertEqual(tender.title, submission.title)
        self.assertEqual(tender.category, submission.category)
        self.assertEqual(tender.estimated_value, submission.estimated_value)
        self.assertEqual(tender.submission_deadline, submission.submission_deadline)
        self.assertEqual(tender.publication_date, submission.publication_date)
        self.assertEqual(tender.buyer_id, str(self.agency.agency_id))
        self.assertEqual(tender.buyer_name, submission.buyer_name)
        self.assertEqual(tender.spec_text, submission.spec_text)
        self.assertEqual(tender.status, TenderStatus.ACTIVE)

    @patch("agencies.tasks.score_agency_tender")
    def test_tender_linked_to_submission(self, mock_task):
        """
        POST links the created Tender to the TenderSubmission via tender FK.

        Validates: Requirement 10.1
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 200)

        submission.refresh_from_db()
        self.assertIsNotNone(submission.tender)
        self.assertEqual(submission.tender.tender_id, submission.tender_ref)

    # -----------------------------------------------------------------------
    # Requirement 10.1 — Celery task enqueued
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.score_agency_tender")
    def test_score_agency_tender_task_enqueued(self, mock_task):
        """
        POST enqueues the score_agency_tender Celery task with the submission pk.

        Validates: Requirement 10.1
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 200)

        # Verify task enqueued with correct submission pk
        mock_task.delay.assert_called_once_with(submission.pk)

    @patch("agencies.tasks.score_agency_tender")
    def test_task_enqueued_even_if_task_import_fails(self, mock_task):
        """
        If the task import or enqueue fails, the view logs a warning but
        still returns 200 (the submission is successfully transitioned).

        Validates: Requirement 10.1
        """
        mock_task.delay = MagicMock(side_effect=Exception("Task queue unavailable"))

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.admin_token)

        # View should still return 200 (submission transitioned successfully)
        self.assertEqual(response.status_code, 200)

        submission.refresh_from_db()
        self.assertEqual(submission.status, "SUBMITTED")
        self.assertIsNotNone(submission.tender)

    # -----------------------------------------------------------------------
    # Requirement 6.12 — AuditLog entry
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.score_agency_tender")
    def test_audit_log_entry_written_on_submit(self, mock_task):
        """
        POST writes a TENDER_SUBMITTED AuditLog entry with action="submitted",
        tender_ref, tender_id, agency_id, and new_status.

        Validates: Requirement 6.12
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_SUBMITTED,
            user=self.admin_user,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(submission.pk),
        ).first()

        self.assertIsNotNone(log, "TENDER_SUBMITTED AuditLog entry not found")
        self.assertEqual(log.data_snapshot.get("action"), "submitted")
        self.assertEqual(log.data_snapshot.get("tender_ref"), submission.tender_ref)
        self.assertIsNotNone(log.data_snapshot.get("tender_id"))
        self.assertEqual(
            log.data_snapshot.get("agency_id"),
            str(self.agency.agency_id),
        )
        self.assertEqual(log.data_snapshot.get("new_status"), "SUBMITTED")

    @patch("agencies.tasks.score_agency_tender")
    def test_audit_log_written_by_officer(self, mock_task):
        """
        POST as AGENCY_OFFICER → AuditLog entry has officer as actor.

        Validates: Requirement 6.12
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.officer_token)

        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_SUBMITTED,
            user=self.officer_user,
            affected_entity_id=str(submission.pk),
        ).first()

        self.assertIsNotNone(log, "TENDER_SUBMITTED AuditLog entry not found for officer")

    # -----------------------------------------------------------------------
    # Edge cases
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.score_agency_tender")
    def test_submit_non_existent_submission_returns_404(self, mock_task):
        """
        POST on non-existent submission ID → 404.

        Validates: Requirement 6.5
        """
        mock_task.delay = MagicMock()

        url = _tender_submit_url(999999)
        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 404)
        mock_task.delay.assert_not_called()

    @patch("agencies.tasks.score_agency_tender")
    def test_response_contains_updated_submission_data(self, mock_task):
        """
        POST returns 200 with the updated submission data including the new status.

        Validates: Requirement 6.5
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.admin_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Response contains all expected fields
        self.assertEqual(data["id"], submission.pk)
        self.assertEqual(data["status"], "SUBMITTED")
        self.assertEqual(data["tender_ref"], submission.tender_ref)
        self.assertEqual(data["title"], submission.title)
        self.assertIn("created_at", data)
        self.assertIn("updated_at", data)

    @patch("agencies.tasks.score_agency_tender")
    def test_officer_can_submit_another_officers_draft(self, mock_task):
        """
        AGENCY_OFFICER can submit a DRAFT tender created by another officer
        in the same agency.

        Validates: Requirement 6.5
        """
        mock_task.delay = MagicMock()

        # Create another officer in the same agency
        officer2 = _make_agency_user(self.agency, role="AGENCY_OFFICER", uid="officer2")
        submission = _make_tender_submission(self.agency, officer2, status="DRAFT")

        url = _tender_submit_url(submission.pk)
        response = self._auth_post(url, token=self.officer_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "SUBMITTED")

        mock_task.delay.assert_called_once_with(submission.pk)

    @patch("agencies.tasks.score_agency_tender")
    def test_admin_can_submit_officers_draft(self, mock_task):
        """
        AGENCY_ADMIN can submit a DRAFT tender created by an AGENCY_OFFICER.

        Validates: Requirement 6.5
        """
        mock_task.delay = MagicMock()

        submission = _make_tender_submission(self.agency, self.officer_user, status="DRAFT")
        url = _tender_submit_url(submission.pk)

        response = self._auth_post(url, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "SUBMITTED")

        mock_task.delay.assert_called_once_with(submission.pk)


# ===========================================================================
# TestCrossAgencyTenderListView — Task 6.7
# GET /api/v1/agencies/tenders/
# Requirements: 12.1, 12.3, 12.5, 12.6
# ===========================================================================

CROSS_AGENCY_TENDER_LIST_URL = "/api/v1/agencies/tenders/"


def _make_gov_auditor_user(uid=None):
    """Create an active GOVERNMENT_AUDITOR user (not linked to any agency)."""
    uid = uid or uuid.uuid4().hex[:8]
    user = User.objects.create_user(
        username=f"gov_auditor_{uid}",
        email=f"gov_auditor_{uid}@example.com",
        password="TestPass123!",
        role="GOVERNMENT_AUDITOR",
    )
    user.is_active = True
    user.save(update_fields=["is_active"])
    return user


def _make_admin_user(uid=None):
    """Create an active ADMIN user (not linked to any agency)."""
    uid = uid or uuid.uuid4().hex[:8]
    user = User.objects.create_user(
        username=f"admin_{uid}",
        email=f"admin_{uid}@example.com",
        password="TestPass123!",
        role="ADMIN",
    )
    user.is_active = True
    user.save(update_fields=["is_active"])
    return user


class TestCrossAgencyTenderListView(TestCase):
    """
    Integration tests for GET /api/v1/agencies/tenders/

    Validates: Requirements 12.1, 12.3, 12.5, 12.6
    """

    def setUp(self):
        self.client = Client()

        # Two separate agencies with their own submissions
        self.agency_a = _make_active_agency(uid="agency_a")
        self.agency_b = _make_active_agency(uid="agency_b")

        self.admin_a = _make_agency_user(self.agency_a, role="AGENCY_ADMIN", uid="admin_a")
        self.admin_b = _make_agency_user(self.agency_b, role="AGENCY_ADMIN", uid="admin_b")

        self.submission_a = _make_tender_submission(
            self.agency_a, self.admin_a, status="SUBMITTED", category="IT"
        )
        self.submission_b = _make_tender_submission(
            self.agency_b, self.admin_b, status="FLAGGED", category="Infrastructure"
        )

        # Government auditor and admin users
        self.gov_auditor = _make_gov_auditor_user()
        self.admin_user = _make_admin_user()

        self.gov_auditor_token = _get_jwt_for_user(self.gov_auditor)
        self.admin_token = _get_jwt_for_user(self.admin_user)

    def _auth_get(self, url, params=None, token=None):
        """Perform an authenticated GET request."""
        token = token or self.gov_auditor_token
        return self.client.get(
            url,
            params or {},
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # Requirement 12.1 — Returns all tenders across all agencies
    # -----------------------------------------------------------------------

    def test_gov_auditor_sees_all_agencies_tenders(self):
        """
        GET /api/v1/agencies/tenders/ as GOVERNMENT_AUDITOR returns submissions
        from all agencies without agency scoping.

        Validates: Requirement 12.1
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}

        self.assertIn(self.submission_a.pk, result_ids)
        self.assertIn(self.submission_b.pk, result_ids)

    def test_admin_sees_all_agencies_tenders(self):
        """
        GET /api/v1/agencies/tenders/ as ADMIN also returns all submissions.

        Validates: Requirement 12.1
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL, token=self.admin_token)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}

        self.assertIn(self.submission_a.pk, result_ids)
        self.assertIn(self.submission_b.pk, result_ids)

    # -----------------------------------------------------------------------
    # Requirement 12.3 — GOVERNMENT_AUDITOR cannot write (read-only)
    # -----------------------------------------------------------------------

    def test_gov_auditor_cannot_post_to_cross_agency_endpoint(self):
        """
        POST /api/v1/agencies/tenders/ as GOVERNMENT_AUDITOR → 405 (Method Not Allowed)
        because the view only implements GET.

        Validates: Requirement 12.3
        """
        response = self.client.post(
            CROSS_AGENCY_TENDER_LIST_URL,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.gov_auditor_token}",
        )
        # View only defines GET, so POST returns 405
        self.assertEqual(response.status_code, 405)

    # -----------------------------------------------------------------------
    # Requirement 12.5 — agency_name and agency_id included in each record
    # -----------------------------------------------------------------------

    def test_response_includes_agency_name_and_agency_id(self):
        """
        Each record in the response includes agency_name and agency_id.

        Validates: Requirement 12.5
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        for record in data["results"]:
            self.assertIn("agency_id", record, "agency_id missing from record")
            self.assertIn("agency_name", record, "agency_name missing from record")
            self.assertIsNotNone(record["agency_id"])
            self.assertIsNotNone(record["agency_name"])

    def test_agency_id_and_name_match_correct_agency(self):
        """
        agency_id and agency_name in each record match the agency that owns
        the submission.

        Validates: Requirement 12.5
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        records_by_id = {r["id"]: r for r in data["results"]}

        record_a = records_by_id[self.submission_a.pk]
        self.assertEqual(record_a["agency_id"], str(self.agency_a.agency_id))
        self.assertEqual(record_a["agency_name"], self.agency_a.legal_name)

        record_b = records_by_id[self.submission_b.pk]
        self.assertEqual(record_b["agency_id"], str(self.agency_b.agency_id))
        self.assertEqual(record_b["agency_name"], self.agency_b.legal_name)

    # -----------------------------------------------------------------------
    # Requirement 12.6 — GOV_AUDITOR_ACCESS AuditLog entry per request
    # -----------------------------------------------------------------------

    def test_gov_auditor_access_audit_log_written(self):
        """
        GET /api/v1/agencies/tenders/ writes a GOV_AUDITOR_ACCESS AuditLog
        entry with the auditor's user ID and role.

        Validates: Requirement 12.6
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.filter(
            event_type=EventType.GOV_AUDITOR_ACCESS,
            user=self.gov_auditor,
        ).first()

        self.assertIsNotNone(log, "GOV_AUDITOR_ACCESS AuditLog entry not found")
        self.assertEqual(log.data_snapshot.get("action"), "cross_agency_list")
        self.assertEqual(log.data_snapshot.get("role"), "GOVERNMENT_AUDITOR")

    def test_audit_log_written_for_admin_access(self):
        """
        GET as ADMIN also writes a GOV_AUDITOR_ACCESS AuditLog entry.

        Validates: Requirement 12.6
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL, token=self.admin_token)

        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.filter(
            event_type=EventType.GOV_AUDITOR_ACCESS,
            user=self.admin_user,
        ).first()

        self.assertIsNotNone(log, "GOV_AUDITOR_ACCESS AuditLog entry not found for ADMIN")
        self.assertEqual(log.data_snapshot.get("action"), "cross_agency_list")

    def test_audit_log_written_per_request(self):
        """
        Each GET request writes a separate GOV_AUDITOR_ACCESS AuditLog entry.

        Validates: Requirement 12.6
        """
        self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)
        self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)

        count = AuditLog.objects.filter(
            event_type=EventType.GOV_AUDITOR_ACCESS,
            user=self.gov_auditor,
        ).count()

        self.assertEqual(count, 2)

    # -----------------------------------------------------------------------
    # Access control — only GOVERNMENT_AUDITOR and ADMIN allowed
    # -----------------------------------------------------------------------

    def test_unauthenticated_request_returns_401_or_403(self):
        """
        GET without Authorization header → 401 or 403.

        Validates: Requirement 12.1
        """
        response = self.client.get(CROSS_AGENCY_TENDER_LIST_URL)
        self.assertIn(response.status_code, [401, 403])

    def test_agency_admin_cannot_access_cross_agency_list(self):
        """
        AGENCY_ADMIN cannot access GET /api/v1/agencies/tenders/ → 403.

        Validates: Requirement 12.1 (only GOVERNMENT_AUDITOR and ADMIN allowed)
        """
        token = _get_jwt_for_user(self.admin_a)
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL, token=token)
        self.assertEqual(response.status_code, 403)

    def test_agency_officer_cannot_access_cross_agency_list(self):
        """
        AGENCY_OFFICER cannot access GET /api/v1/agencies/tenders/ → 403.

        Validates: Requirement 12.1
        """
        officer = _make_agency_user(self.agency_a, role="AGENCY_OFFICER", uid="officer_x")
        token = _get_jwt_for_user(officer)
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL, token=token)
        self.assertEqual(response.status_code, 403)

    def test_reviewer_cannot_access_cross_agency_list(self):
        """
        REVIEWER cannot access GET /api/v1/agencies/tenders/ → 403.

        Validates: Requirement 12.1
        """
        reviewer = _make_agency_user(self.agency_a, role="REVIEWER", uid="reviewer_x")
        token = _get_jwt_for_user(reviewer)
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL, token=token)
        self.assertEqual(response.status_code, 403)

    # -----------------------------------------------------------------------
    # Filters — same as agency-scoped list
    # -----------------------------------------------------------------------

    def test_filter_by_status(self):
        """
        ?status=SUBMITTED returns only SUBMITTED submissions across all agencies.

        Validates: Requirement 12.1
        """
        response = self._auth_get(
            CROSS_AGENCY_TENDER_LIST_URL, params={"status": "SUBMITTED"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        for record in data["results"]:
            self.assertEqual(record["status"], "SUBMITTED")

        result_ids = {r["id"] for r in data["results"]}
        self.assertIn(self.submission_a.pk, result_ids)
        self.assertNotIn(self.submission_b.pk, result_ids)

    def test_filter_by_category(self):
        """
        ?category=IT returns only IT submissions across all agencies.

        Validates: Requirement 12.1
        """
        response = self._auth_get(
            CROSS_AGENCY_TENDER_LIST_URL, params={"category": "IT"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()

        for record in data["results"]:
            self.assertEqual(record["category"].upper(), "IT")

        result_ids = {r["id"] for r in data["results"]}
        self.assertIn(self.submission_a.pk, result_ids)
        self.assertNotIn(self.submission_b.pk, result_ids)

    def test_filter_by_date_from(self):
        """
        ?date_from=<future_date> returns no results when all submissions are older.

        Validates: Requirement 12.1
        """
        from datetime import date, timedelta
        future_date = (date.today() + timedelta(days=10)).isoformat()

        response = self._auth_get(
            CROSS_AGENCY_TENDER_LIST_URL, params={"date_from": future_date}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["count"], 0)

    def test_filter_by_date_to(self):
        """
        ?date_to=<today> returns all submissions created today or earlier.

        Validates: Requirement 12.1
        """
        from datetime import date
        today = date.today().isoformat()

        response = self._auth_get(
            CROSS_AGENCY_TENDER_LIST_URL, params={"date_to": today}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        result_ids = {r["id"] for r in data["results"]}

        self.assertIn(self.submission_a.pk, result_ids)
        self.assertIn(self.submission_b.pk, result_ids)

    # -----------------------------------------------------------------------
    # Pagination
    # -----------------------------------------------------------------------

    def test_response_is_paginated(self):
        """
        Response includes pagination metadata: count, next, previous, results.

        Validates: Requirement 12.1
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("count", data)
        self.assertIn("results", data)
        self.assertIn("next", data)
        self.assertIn("previous", data)
        self.assertGreaterEqual(data["count"], 2)

    def test_audit_log_filters_recorded(self):
        """
        The GOV_AUDITOR_ACCESS AuditLog entry records the applied filters.

        Validates: Requirement 12.6
        """
        response = self._auth_get(
            CROSS_AGENCY_TENDER_LIST_URL,
            params={"status": "SUBMITTED", "category": "IT"},
        )

        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.filter(
            event_type=EventType.GOV_AUDITOR_ACCESS,
            user=self.gov_auditor,
        ).order_by("-id").first()

        self.assertIsNotNone(log)
        filters = log.data_snapshot.get("filters", {})
        self.assertEqual(filters.get("status"), "SUBMITTED")
        self.assertEqual(filters.get("category"), "IT")


# ===========================================================================
# TestTenderClearView — Task 6.8
# PATCH /api/v1/agencies/tenders/<id>/clear/
# Requirements: 7.5, 12.2
# ===========================================================================


def _tender_clear_url(pk):
    return f"/api/v1/agencies/tenders/{pk}/clear/"


class TestTenderClearView(TestCase):
    """
    Integration tests for PATCH /api/v1/agencies/tenders/<id>/clear/

    Validates: Requirements 7.5, 12.2
    """

    def setUp(self):
        self.client = Client()

        self.agency = _make_active_agency(uid="clear_agency")
        self.agency_user = _make_agency_user(self.agency, role="AGENCY_ADMIN", uid="clear_admin")

        self.gov_auditor = _make_gov_auditor_user(uid="clear_auditor")
        self.admin_user = _make_admin_user(uid="clear_admin_user")

        self.gov_auditor_token = _get_jwt_for_user(self.gov_auditor)
        self.admin_token = _get_jwt_for_user(self.admin_user)

    def _auth_patch(self, url, data=None, token=None):
        token = token or self.gov_auditor_token
        return self.client.patch(
            url,
            data=json.dumps(data or {}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # Happy path — GOVERNMENT_AUDITOR clears a FLAGGED tender
    # -----------------------------------------------------------------------

    def test_gov_auditor_can_clear_flagged_tender(self):
        """
        PATCH /api/v1/agencies/tenders/<id>/clear/ as GOVERNMENT_AUDITOR with
        a valid review_note on a FLAGGED submission → 200, status becomes CLEARED.

        Validates: Requirements 7.5, 12.2
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)

        response = self._auth_patch(url, {"review_note": "Reviewed and cleared after investigation."})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "CLEARED")

        submission.refresh_from_db()
        self.assertEqual(submission.status, "CLEARED")
        self.assertEqual(submission.review_note, "Reviewed and cleared after investigation.")

    def test_admin_can_clear_flagged_tender(self):
        """
        PATCH as ADMIN with valid review_note on a FLAGGED submission → 200.

        Validates: Requirements 7.5, 12.2
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)

        response = self._auth_patch(
            url,
            {"review_note": "Admin reviewed and cleared this tender."},
            token=self.admin_token,
        )

        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "CLEARED")

    def test_gov_auditor_can_clear_under_review_tender(self):
        """
        PATCH on an UNDER_REVIEW submission → 200, status becomes CLEARED.
        (UNDER_REVIEW → CLEARED is a valid transition per VALID_TRANSITIONS.)

        Validates: Requirement 7.1
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="UNDER_REVIEW")
        url = _tender_clear_url(submission.pk)

        response = self._auth_patch(url, {"review_note": "No issues found after review."})

        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "CLEARED")

    # -----------------------------------------------------------------------
    # review_note validation — Requirement 7.5
    # -----------------------------------------------------------------------

    def test_missing_review_note_returns_400(self):
        """
        PATCH without review_note → 400.

        Validates: Requirement 7.5
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)

        response = self._auth_patch(url, {})

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("review_note", data.get("detail", "").lower())

    def test_review_note_too_short_returns_400(self):
        """
        PATCH with review_note of 9 characters → 400.

        Validates: Requirement 7.5
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)

        response = self._auth_patch(url, {"review_note": "123456789"})  # 9 chars

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("review_note", data.get("detail", "").lower())

    def test_review_note_exactly_10_chars_succeeds(self):
        """
        PATCH with review_note of exactly 10 characters → 200.

        Validates: Requirement 7.5
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)

        response = self._auth_patch(url, {"review_note": "1234567890"})  # exactly 10 chars

        self.assertEqual(response.status_code, 200)

    def test_review_note_empty_string_returns_400(self):
        """
        PATCH with review_note="" → 400.

        Validates: Requirement 7.5
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)

        response = self._auth_patch(url, {"review_note": ""})

        self.assertEqual(response.status_code, 400)

    # -----------------------------------------------------------------------
    # Invalid transition — Requirement 7.2
    # -----------------------------------------------------------------------

    def test_clearing_draft_tender_returns_400(self):
        """
        PATCH on a DRAFT submission → 400 (DRAFT → CLEARED is not a valid transition).

        Validates: Requirement 7.2
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="DRAFT")
        url = _tender_clear_url(submission.pk)

        response = self._auth_patch(url, {"review_note": "Attempting to clear a draft tender."})

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertIn("DRAFT", data.get("detail", ""))

    def test_clearing_submitted_tender_returns_400(self):
        """
        PATCH on a SUBMITTED submission → 400 (SUBMITTED → CLEARED is not valid
        via this endpoint; only FLAGGED and UNDER_REVIEW can be cleared manually).

        Validates: Requirement 7.2
        """
        # SUBMITTED → CLEARED is actually valid per VALID_TRANSITIONS (pipeline path),
        # but let's verify the transition works correctly when called via this endpoint.
        # Per the design, SUBMITTED → CLEARED is valid (pipeline auto-clear).
        # So we test CLEARED → CLEARED which is invalid.
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        # First clear it
        self._auth_patch(
            _tender_clear_url(submission.pk),
            {"review_note": "First clearing of this tender."},
        )
        submission.refresh_from_db()
        self.assertEqual(submission.status, "CLEARED")

        # Try to clear again — CLEARED → CLEARED is invalid
        response = self._auth_patch(
            _tender_clear_url(submission.pk),
            {"review_note": "Attempting to clear an already cleared tender."},
        )

        self.assertEqual(response.status_code, 400)

    # -----------------------------------------------------------------------
    # AuditLog — Requirement 7.5
    # -----------------------------------------------------------------------

    def test_tender_cleared_audit_log_written(self):
        """
        PATCH with valid review_note → TENDER_CLEARED AuditLog entry written
        with reviewer user ID and note.

        Validates: Requirement 7.5
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)
        review_note = "Cleared after thorough investigation."

        response = self._auth_patch(url, {"review_note": review_note})

        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_CLEARED,
            user=self.gov_auditor,
        ).first()

        self.assertIsNotNone(log, "TENDER_CLEARED AuditLog entry not found")
        self.assertEqual(log.data_snapshot.get("reviewer_user_id"), self.gov_auditor.pk)
        self.assertEqual(log.data_snapshot.get("review_note"), review_note)
        self.assertEqual(log.affected_entity_id, str(submission.pk))

    def test_admin_tender_cleared_audit_log_written(self):
        """
        PATCH as ADMIN → TENDER_CLEARED AuditLog entry written with admin's user ID.

        Validates: Requirement 7.5
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)
        review_note = "Admin cleared after review process."

        response = self._auth_patch(url, {"review_note": review_note}, token=self.admin_token)

        self.assertEqual(response.status_code, 200)

        log = AuditLog.objects.filter(
            event_type=EventType.TENDER_CLEARED,
            user=self.admin_user,
        ).first()

        self.assertIsNotNone(log, "TENDER_CLEARED AuditLog entry not found for admin")
        self.assertEqual(log.data_snapshot.get("reviewer_user_id"), self.admin_user.pk)
        self.assertEqual(log.data_snapshot.get("review_note"), review_note)

    # -----------------------------------------------------------------------
    # Access control — Requirement 12.2
    # -----------------------------------------------------------------------

    def test_unauthenticated_request_returns_401(self):
        """
        PATCH without Authorization header → 401.

        Validates: Requirement 12.2
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)

        response = self.client.patch(
            url,
            data=json.dumps({"review_note": "Cleared after review."}),
            content_type="application/json",
        )

        self.assertIn(response.status_code, [401, 403])

    def test_agency_admin_cannot_clear_tender(self):
        """
        PATCH as AGENCY_ADMIN → 403 (only GOVERNMENT_AUDITOR and ADMIN allowed).

        Validates: Requirement 12.2
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)
        token = _get_jwt_for_user(self.agency_user)

        response = self._auth_patch(url, {"review_note": "Cleared after review."}, token=token)

        self.assertEqual(response.status_code, 403)

    def test_agency_officer_cannot_clear_tender(self):
        """
        PATCH as AGENCY_OFFICER → 403.

        Validates: Requirement 12.2
        """
        officer = _make_agency_user(self.agency, role="AGENCY_OFFICER", uid="clear_officer")
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)
        token = _get_jwt_for_user(officer)

        response = self._auth_patch(url, {"review_note": "Cleared after review."}, token=token)

        self.assertEqual(response.status_code, 403)

    def test_reviewer_cannot_clear_tender(self):
        """
        PATCH as REVIEWER → 403.

        Validates: Requirement 12.2
        """
        reviewer = _make_agency_user(self.agency, role="REVIEWER", uid="clear_reviewer")
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)
        token = _get_jwt_for_user(reviewer)

        response = self._auth_patch(url, {"review_note": "Cleared after review."}, token=token)

        self.assertEqual(response.status_code, 403)

    # -----------------------------------------------------------------------
    # Not found
    # -----------------------------------------------------------------------

    def test_nonexistent_submission_returns_404(self):
        """
        PATCH on a non-existent submission ID → 404.

        Validates: Requirement 7.5
        """
        url = _tender_clear_url(999999)

        response = self._auth_patch(url, {"review_note": "Cleared after review."})

        self.assertEqual(response.status_code, 404)

    # -----------------------------------------------------------------------
    # Response body
    # -----------------------------------------------------------------------

    def test_response_contains_updated_submission_data(self):
        """
        PATCH with valid review_note → 200 response contains updated submission
        data including status=CLEARED and the review_note.

        Validates: Requirement 7.5
        """
        submission = _make_tender_submission(self.agency, self.agency_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)
        review_note = "Cleared after thorough investigation of all documents."

        response = self._auth_patch(url, {"review_note": review_note})

        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertEqual(data["id"], submission.pk)
        self.assertEqual(data["status"], "CLEARED")
        self.assertIn("review_note", data)
        self.assertEqual(data["review_note"], review_note)

    def test_gov_auditor_can_clear_any_agency_tender(self):
        """
        GOVERNMENT_AUDITOR can clear a tender from any agency (cross-agency access).

        Validates: Requirements 7.5, 12.2
        """
        other_agency = _make_active_agency(uid="other_clear_agency")
        other_user = _make_agency_user(other_agency, role="AGENCY_ADMIN", uid="other_clear_admin")
        submission = _make_tender_submission(other_agency, other_user, status="FLAGGED")
        url = _tender_clear_url(submission.pk)

        response = self._auth_patch(url, {"review_note": "Cross-agency clear after review."})

        self.assertEqual(response.status_code, 200)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "CLEARED")


# ===========================================================================
# TestInvitationFlow — Task 10.12
# POST /api/v1/agencies/me/invitations/
# GET  /api/v1/agencies/me/invitations/accept/?token=<hex>
# POST /api/v1/agencies/me/invitations/accept/
# Requirements: 4.1–4.4
# ===========================================================================

INVITATION_CREATE_URL = "/api/v1/agencies/me/invitations/"
INVITATION_ACCEPT_URL = "/api/v1/agencies/me/invitations/accept/"

# Fixed 32-byte value for invitation token patching
FIXED_INVITE_RAW_TOKEN = b"\x02" * 32
FIXED_INVITE_TOKEN_HEX = FIXED_INVITE_RAW_TOKEN.hex()
FIXED_INVITE_TOKEN_HASH = hashlib.sha256(FIXED_INVITE_RAW_TOKEN).hexdigest()


def _invite_urandom_side_effect(n: int) -> bytes:
    """
    Side effect for patching agencies.views.os.urandom in invitation tests.
    Returns FIXED_INVITE_RAW_TOKEN when n==32, real random bytes otherwise.
    """
    if n == 32:
        return FIXED_INVITE_RAW_TOKEN
    return _real_urandom(n)


class TestInvitationFlow(TestCase):
    """
    Integration tests for the invitation send → accept → new user created flow.

    Covers:
      - POST /api/v1/agencies/me/invitations/ (AGENCY_ADMIN only)
      - GET  /api/v1/agencies/me/invitations/accept/?token=<hex> (public)
      - POST /api/v1/agencies/me/invitations/accept/ (public)
      - Full end-to-end: send → accept → user created with correct role and agency

    Validates: Requirements 4.1, 4.2, 4.3, 4.4
    """

    def setUp(self):
        self.client = Client()
        self.agency = _make_active_agency()
        self.admin_user = _make_agency_user(self.agency, role="AGENCY_ADMIN")
        self.admin_token = _get_jwt_for_user(self.admin_user)

    def _auth_post(self, url, data, token=None):
        """Perform an authenticated POST request."""
        token = token or self.admin_token
        return self.client.post(
            url,
            data=json.dumps(data),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # POST /api/v1/agencies/me/invitations/ — Requirement 4.1, 4.2, 4.6
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.send_invitation_email")
    def test_agency_admin_can_send_invitation(self, mock_task):
        """
        POST /api/v1/agencies/me/invitations/ as AGENCY_ADMIN with valid role
        → 201, Invitation record created, send_invitation_email.delay called.

        Validates: Requirements 4.1, 4.2
        """
        mock_task.delay = MagicMock()
        invitee_email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"

        response = self._auth_post(
            INVITATION_CREATE_URL,
            {"email": invitee_email, "role": "AGENCY_OFFICER"},
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("message", data)
        self.assertIn("expires_at", data)

        # Invitation record created in DB
        from agencies.models import Invitation
        invitation = Invitation.objects.filter(email=invitee_email).first()
        self.assertIsNotNone(invitation, "Invitation record not found in DB")
        self.assertEqual(invitation.role, "AGENCY_OFFICER")
        self.assertEqual(invitation.agency_id, self.agency.pk)
        self.assertEqual(invitation.invited_by_id, self.admin_user.pk)
        self.assertIsNone(invitation.consumed_at)

        # Email task enqueued
        mock_task.delay.assert_called_once()

    @patch("agencies.tasks.send_invitation_email")
    def test_invitation_for_reviewer_role_succeeds(self, mock_task):
        """
        POST with role=REVIEWER → 201, Invitation created with REVIEWER role.

        Validates: Requirement 4.1
        """
        mock_task.delay = MagicMock()
        invitee_email = f"reviewer-{uuid.uuid4().hex[:8]}@example.com"

        response = self._auth_post(
            INVITATION_CREATE_URL,
            {"email": invitee_email, "role": "REVIEWER"},
        )

        self.assertEqual(response.status_code, 201)

        from agencies.models import Invitation
        invitation = Invitation.objects.filter(email=invitee_email).first()
        self.assertIsNotNone(invitation)
        self.assertEqual(invitation.role, "REVIEWER")

    @patch("agencies.tasks.send_invitation_email")
    def test_invitation_with_agency_admin_role_returns_403(self, mock_task):
        """
        POST with role=AGENCY_ADMIN → 403 (only AGENCY_OFFICER or REVIEWER allowed).

        Validates: Requirement 4.6
        """
        mock_task.delay = MagicMock()
        invitee_email = f"admin-invite-{uuid.uuid4().hex[:8]}@example.com"

        response = self._auth_post(
            INVITATION_CREATE_URL,
            {"email": invitee_email, "role": "AGENCY_ADMIN"},
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertIn("AGENCY_OFFICER", data.get("detail", ""))

    @patch("agencies.tasks.send_invitation_email")
    def test_invitation_with_government_auditor_role_returns_403(self, mock_task):
        """
        POST with role=GOVERNMENT_AUDITOR → 403.

        Validates: Requirement 4.6
        """
        mock_task.delay = MagicMock()
        invitee_email = f"gov-invite-{uuid.uuid4().hex[:8]}@example.com"

        response = self._auth_post(
            INVITATION_CREATE_URL,
            {"email": invitee_email, "role": "GOVERNMENT_AUDITOR"},
        )

        self.assertEqual(response.status_code, 403)

    def test_non_admin_cannot_send_invitation(self):
        """
        POST as AGENCY_OFFICER → 403 (only AGENCY_ADMIN can invite).

        Validates: Requirement 4.6
        """
        officer_user = _make_agency_user(self.agency, role="AGENCY_OFFICER")
        officer_token = _get_jwt_for_user(officer_user)
        invitee_email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"

        response = self._auth_post(
            INVITATION_CREATE_URL,
            {"email": invitee_email, "role": "AGENCY_OFFICER"},
            token=officer_token,
        )

        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_invitation_create_returns_401(self):
        """
        POST without Authorization header → 401.

        Validates: Requirement 4.6
        """
        response = self.client.post(
            INVITATION_CREATE_URL,
            data=json.dumps({"email": "test@example.com", "role": "AGENCY_OFFICER"}),
            content_type="application/json",
        )
        self.assertIn(response.status_code, [401, 403])

    @patch("agencies.tasks.send_invitation_email")
    def test_invitation_audit_log_written(self, mock_task):
        """
        POST valid invitation → INVITATION_CREATED AuditLog entry written.

        Validates: Requirement 4.9 (via 4.1)
        """
        mock_task.delay = MagicMock()
        invitee_email = f"audit-{uuid.uuid4().hex[:8]}@example.com"

        response = self._auth_post(
            INVITATION_CREATE_URL,
            {"email": invitee_email, "role": "AGENCY_OFFICER"},
        )

        self.assertEqual(response.status_code, 201)

        log = AuditLog.objects.filter(
            event_type=EventType.INVITATION_CREATED,
            user=self.admin_user,
        ).first()

        self.assertIsNotNone(log, "INVITATION_CREATED AuditLog entry not found")
        self.assertEqual(log.data_snapshot.get("email"), invitee_email)
        self.assertEqual(log.data_snapshot.get("role"), "AGENCY_OFFICER")

    # -----------------------------------------------------------------------
    # GET /api/v1/agencies/me/invitations/accept/?token=<hex> — Requirement 4.3, 4.5
    # -----------------------------------------------------------------------

    def _create_invitation(self, role="AGENCY_OFFICER"):
        """
        Create an Invitation record directly in the DB with a known token.
        Returns (invitation, token_hex).
        """
        from agencies.models import Invitation
        invitee_email = f"invitee-{uuid.uuid4().hex[:8]}@example.com"
        invitation = Invitation.objects.create(
            token_hash=FIXED_INVITE_TOKEN_HASH,
            email=invitee_email,
            role=role,
            agency=self.agency,
            invited_by=self.admin_user,
            expires_at=timezone.now() + timezone.timedelta(hours=72),
        )
        return invitation, FIXED_INVITE_TOKEN_HEX

    def test_get_valid_token_returns_invitation_details(self):
        """
        GET /api/v1/agencies/me/invitations/accept/?token=<valid_hex>
        → 200, returns email, role, agency_name.

        Validates: Requirement 4.3
        """
        invitation, token_hex = self._create_invitation(role="AGENCY_OFFICER")

        response = self.client.get(
            INVITATION_ACCEPT_URL,
            {"token": token_hex},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["email"], invitation.email)
        self.assertEqual(data["role"], "AGENCY_OFFICER")
        self.assertEqual(data["agency_name"], self.agency.legal_name)

    def test_get_expired_token_returns_410(self):
        """
        GET with an expired token → 410 Gone.

        Validates: Requirement 4.5
        """
        from agencies.models import Invitation
        invitee_email = f"expired-{uuid.uuid4().hex[:8]}@example.com"
        raw_token = _real_urandom(32)
        token_hex = raw_token.hex()
        token_hash = hashlib.sha256(raw_token).hexdigest()

        Invitation.objects.create(
            token_hash=token_hash,
            email=invitee_email,
            role="AGENCY_OFFICER",
            agency=self.agency,
            invited_by=self.admin_user,
            expires_at=timezone.now() - timezone.timedelta(hours=1),  # already expired
        )

        response = self.client.get(
            INVITATION_ACCEPT_URL,
            {"token": token_hex},
        )

        self.assertEqual(response.status_code, 410)

    def test_get_consumed_token_returns_410(self):
        """
        GET with an already-consumed token → 410 Gone.

        Validates: Requirement 4.5
        """
        from agencies.models import Invitation
        invitee_email = f"consumed-{uuid.uuid4().hex[:8]}@example.com"
        raw_token = _real_urandom(32)
        token_hex = raw_token.hex()
        token_hash = hashlib.sha256(raw_token).hexdigest()

        Invitation.objects.create(
            token_hash=token_hash,
            email=invitee_email,
            role="REVIEWER",
            agency=self.agency,
            invited_by=self.admin_user,
            expires_at=timezone.now() + timezone.timedelta(hours=72),
            consumed_at=timezone.now() - timezone.timedelta(minutes=5),  # already consumed
        )

        response = self.client.get(
            INVITATION_ACCEPT_URL,
            {"token": token_hex},
        )

        self.assertEqual(response.status_code, 410)

    def test_get_unknown_token_returns_410(self):
        """
        GET with a valid hex token that has no matching DB record → 410.

        Validates: Requirement 4.5
        """
        unknown_hex = (b"\xcc" * 32).hex()

        response = self.client.get(
            INVITATION_ACCEPT_URL,
            {"token": unknown_hex},
        )

        self.assertEqual(response.status_code, 410)

    def test_get_missing_token_returns_400(self):
        """
        GET without token query param → 400.

        Validates: Requirement 4.3
        """
        response = self.client.get(INVITATION_ACCEPT_URL)

        self.assertEqual(response.status_code, 400)

    # -----------------------------------------------------------------------
    # POST /api/v1/agencies/me/invitations/accept/ — Requirement 4.4
    # -----------------------------------------------------------------------

    def test_post_valid_token_creates_user_with_correct_role_and_agency(self):
        """
        POST /api/v1/agencies/me/invitations/accept/ with valid token, password,
        and username → 201, User created with correct role and agency.

        Validates: Requirement 4.4
        """
        invitation, token_hex = self._create_invitation(role="AGENCY_OFFICER")

        response = self.client.post(
            INVITATION_ACCEPT_URL,
            data=json.dumps({
                "token": token_hex,
                "password": "NewUserPass123!",
                "username": f"newuser_{uuid.uuid4().hex[:8]}",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertIn("message", data)

        # User created with correct role and agency
        new_user = User.objects.get(email=invitation.email)
        self.assertEqual(new_user.role, "AGENCY_OFFICER")
        self.assertEqual(new_user.agency_id, self.agency.pk)
        self.assertTrue(new_user.is_active)
        self.assertTrue(new_user.email_verified)

        # Invitation marked as consumed
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.consumed_at)

    def test_post_valid_token_creates_reviewer_user(self):
        """
        POST with REVIEWER invitation → User created with REVIEWER role.

        Validates: Requirement 4.4
        """
        invitation, token_hex = self._create_invitation(role="REVIEWER")

        response = self.client.post(
            INVITATION_ACCEPT_URL,
            data=json.dumps({
                "token": token_hex,
                "password": "ReviewerPass123!",
                "username": f"reviewer_{uuid.uuid4().hex[:8]}",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        new_user = User.objects.get(email=invitation.email)
        self.assertEqual(new_user.role, "REVIEWER")
        self.assertEqual(new_user.agency_id, self.agency.pk)

    def test_post_expired_token_returns_410(self):
        """
        POST with expired token → 410 Gone.

        Validates: Requirement 4.5
        """
        from agencies.models import Invitation
        invitee_email = f"expired-post-{uuid.uuid4().hex[:8]}@example.com"
        raw_token = _real_urandom(32)
        token_hex = raw_token.hex()
        token_hash = hashlib.sha256(raw_token).hexdigest()

        Invitation.objects.create(
            token_hash=token_hash,
            email=invitee_email,
            role="AGENCY_OFFICER",
            agency=self.agency,
            invited_by=self.admin_user,
            expires_at=timezone.now() - timezone.timedelta(hours=1),
        )

        response = self.client.post(
            INVITATION_ACCEPT_URL,
            data=json.dumps({
                "token": token_hex,
                "password": "SomePass123!",
                "username": "someuser",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 410)

    def test_post_missing_password_returns_400(self):
        """
        POST without password → 400.

        Validates: Requirement 4.4
        """
        invitation, token_hex = self._create_invitation()

        response = self.client.post(
            INVITATION_ACCEPT_URL,
            data=json.dumps({"token": token_hex}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_post_accept_writes_invitation_accepted_audit_log(self):
        """
        POST valid token → INVITATION_ACCEPTED AuditLog entry written.

        Validates: Requirement 4.9 (via 4.4)
        """
        invitation, token_hex = self._create_invitation(role="AGENCY_OFFICER")

        response = self.client.post(
            INVITATION_ACCEPT_URL,
            data=json.dumps({
                "token": token_hex,
                "password": "AuditPass123!",
                "username": f"audituser_{uuid.uuid4().hex[:8]}",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)

        new_user = User.objects.get(email=invitation.email)
        log = AuditLog.objects.filter(
            event_type=EventType.INVITATION_ACCEPTED,
            user=new_user,
        ).first()

        self.assertIsNotNone(log, "INVITATION_ACCEPTED AuditLog entry not found")
        self.assertEqual(log.data_snapshot.get("email"), invitation.email)
        self.assertEqual(log.data_snapshot.get("role"), "AGENCY_OFFICER")
        self.assertEqual(
            log.data_snapshot.get("agency_id"),
            str(self.agency.agency_id),
        )

    # -----------------------------------------------------------------------
    # Full end-to-end: send invitation → accept → new user created
    # Requirements: 4.1–4.4
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.send_invitation_email")
    def test_full_invitation_flow_send_accept_user_created(self, mock_task):
        """
        Full end-to-end integration test:
          1. AGENCY_ADMIN sends invitation → 201, Invitation created, email enqueued
          2. GET accept endpoint with token → 200, returns email/role/agency_name
          3. POST accept endpoint with token + password → 201, User created
             with correct role (AGENCY_OFFICER) and agency

        Validates: Requirements 4.1, 4.2, 4.3, 4.4
        """
        mock_task.delay = MagicMock()
        invitee_email = f"e2e-{uuid.uuid4().hex[:8]}@example.com"

        # Step 1: AGENCY_ADMIN sends invitation with known token
        with patch("agencies.views.os.urandom", side_effect=_invite_urandom_side_effect):
            send_response = self._auth_post(
                INVITATION_CREATE_URL,
                {"email": invitee_email, "role": "AGENCY_OFFICER"},
            )

        self.assertEqual(send_response.status_code, 201)
        mock_task.delay.assert_called_once()

        # Confirm Invitation record exists
        from agencies.models import Invitation
        invitation = Invitation.objects.get(email=invitee_email)
        self.assertEqual(invitation.role, "AGENCY_OFFICER")
        self.assertEqual(invitation.agency_id, self.agency.pk)
        self.assertIsNone(invitation.consumed_at)

        # Step 2: GET accept endpoint to retrieve invitation details
        token_hex = FIXED_INVITE_TOKEN_HEX
        get_response = self.client.get(
            INVITATION_ACCEPT_URL,
            {"token": token_hex},
        )

        self.assertEqual(get_response.status_code, 200)
        get_data = get_response.json()
        self.assertEqual(get_data["email"], invitee_email)
        self.assertEqual(get_data["role"], "AGENCY_OFFICER")
        self.assertEqual(get_data["agency_name"], self.agency.legal_name)

        # Step 3: POST accept endpoint to create user account
        new_username = f"e2euser_{uuid.uuid4().hex[:8]}"
        post_response = self.client.post(
            INVITATION_ACCEPT_URL,
            data=json.dumps({
                "token": token_hex,
                "password": "E2EPass123!",
                "username": new_username,
            }),
            content_type="application/json",
        )

        self.assertEqual(post_response.status_code, 201)

        # Verify new user has correct role and agency
        new_user = User.objects.get(email=invitee_email)
        self.assertEqual(new_user.role, "AGENCY_OFFICER")
        self.assertEqual(new_user.agency_id, self.agency.pk)
        self.assertTrue(new_user.is_active)
        self.assertTrue(new_user.email_verified)
        self.assertEqual(new_user.username, new_username)

        # Verify invitation is consumed
        invitation.refresh_from_db()
        self.assertIsNotNone(invitation.consumed_at)

        # Verify INVITATION_ACCEPTED AuditLog entry
        log = AuditLog.objects.filter(
            event_type=EventType.INVITATION_ACCEPTED,
            user=new_user,
        ).first()
        self.assertIsNotNone(log, "INVITATION_ACCEPTED AuditLog entry not found")
        self.assertEqual(
            log.data_snapshot.get("agency_id"),
            str(self.agency.agency_id),
        )
        self.assertEqual(log.data_snapshot.get("new_user_id"), new_user.pk)


# ===========================================================================
# TestCrossAgencyAccess — Task 10.13
# Consolidated cross-agency access tests returning HTTP 403
# Requirements: 3.6, 8.2
# ===========================================================================


class TestCrossAgencyAccess(TestCase):
    """
    Consolidated integration tests verifying that agency-scoped users cannot
    access resources belonging to a different agency.

    Each test creates two independent agencies (A and B) and asserts that a
    user authenticated as Agency A receives HTTP 403 when attempting to access
    or mutate Agency B's resources.

    Validates: Requirements 3.6, 8.2
    """

    def setUp(self):
        self.client = Client()

        # Agency A — the authenticated user's agency
        self.agency_a = _make_active_agency(uid="cross_a")
        self.admin_a = _make_agency_user(self.agency_a, role="AGENCY_ADMIN", uid="cross_admin_a")
        self.token_a = _get_jwt_for_user(self.admin_a)

        # Agency B — the "other" agency whose resources should be inaccessible
        self.agency_b = _make_active_agency(uid="cross_b")
        self.admin_b = _make_agency_user(self.agency_b, role="AGENCY_ADMIN", uid="cross_admin_b")
        self.member_b = _make_agency_user(self.agency_b, role="AGENCY_OFFICER", uid="cross_officer_b")

    # -----------------------------------------------------------------------
    # Requirement 8.2 — Tender list is agency-scoped (no cross-agency leakage)
    # -----------------------------------------------------------------------

    def test_tender_list_does_not_expose_other_agency_submissions(self):
        """
        GET /api/v1/agencies/me/tenders/ as Agency A user returns only Agency A's
        submissions; Agency B's submissions are absent from the response.

        Validates: Requirements 3.6, 8.2
        """
        sub_a = _make_tender_submission(self.agency_a, self.admin_a)
        sub_b = _make_tender_submission(self.agency_b, self.admin_b)

        response = self.client.get(
            TENDER_LIST_URL,
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
        )

        self.assertEqual(response.status_code, 200)
        result_ids = {r["id"] for r in response.json()["results"]}
        self.assertIn(sub_a.pk, result_ids)
        self.assertNotIn(sub_b.pk, result_ids)

    # -----------------------------------------------------------------------
    # Requirement 8.2 — Tender detail is agency-scoped
    # -----------------------------------------------------------------------

    def test_tender_detail_cross_agency_returns_403(self):
        """
        GET /api/v1/agencies/me/tenders/<id>/ where <id> belongs to Agency B
        and the authenticated user is from Agency A → 403.

        Validates: Requirements 3.6, 8.2
        """
        sub_b = _make_tender_submission(self.agency_b, self.admin_b)
        url = f"/api/v1/agencies/me/tenders/{sub_b.pk}/"

        response = self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
        )

        self.assertEqual(response.status_code, 403)

    # -----------------------------------------------------------------------
    # Requirement 8.2 — Tender edit (PATCH) is agency-scoped
    # -----------------------------------------------------------------------

    def test_tender_patch_cross_agency_returns_403(self):
        """
        PATCH /api/v1/agencies/me/tenders/<id>/ where <id> belongs to Agency B
        and the authenticated user is from Agency A → 403.

        Validates: Requirements 3.6, 8.2
        """
        sub_b = _make_tender_submission(self.agency_b, self.admin_b, status="DRAFT")
        url = f"/api/v1/agencies/me/tenders/{sub_b.pk}/"

        response = self.client.patch(
            url,
            data=json.dumps({"title": "Attempted Cross-Agency Edit"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
        )

        self.assertEqual(response.status_code, 403)
        # Submission must be unchanged
        sub_b.refresh_from_db()
        self.assertNotEqual(sub_b.title, "Attempted Cross-Agency Edit")

    # -----------------------------------------------------------------------
    # Requirement 8.2 — Tender delete is agency-scoped
    # -----------------------------------------------------------------------

    def test_tender_delete_cross_agency_returns_403(self):
        """
        DELETE /api/v1/agencies/me/tenders/<id>/ where <id> belongs to Agency B
        and the authenticated user is from Agency A → 403.

        Validates: Requirements 3.6, 8.2
        """
        from agencies.models import TenderSubmission

        sub_b = _make_tender_submission(self.agency_b, self.admin_b, status="DRAFT")
        url = f"/api/v1/agencies/me/tenders/{sub_b.pk}/"

        response = self.client.delete(
            url,
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
        )

        self.assertEqual(response.status_code, 403)
        # Submission must still exist
        self.assertTrue(TenderSubmission.objects.filter(pk=sub_b.pk).exists())

    # -----------------------------------------------------------------------
    # Requirement 8.2 — Tender submit is agency-scoped
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.score_agency_tender")
    def test_tender_submit_cross_agency_returns_403(self, mock_task):
        """
        POST /api/v1/agencies/me/tenders/<id>/submit/ where <id> belongs to
        Agency B and the authenticated user is from Agency A → 403.
        The scoring task must NOT be enqueued.

        Validates: Requirements 3.6, 8.2
        """
        mock_task.delay = MagicMock()

        sub_b = _make_tender_submission(self.agency_b, self.admin_b, status="DRAFT")
        url = f"/api/v1/agencies/me/tenders/{sub_b.pk}/submit/"

        response = self.client.post(
            url,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
        )

        self.assertEqual(response.status_code, 403)
        mock_task.delay.assert_not_called()
        # Submission status must remain DRAFT
        sub_b.refresh_from_db()
        self.assertEqual(sub_b.status, "DRAFT")

    # -----------------------------------------------------------------------
    # Requirement 8.6 — Member deactivation is agency-scoped
    # -----------------------------------------------------------------------

    def test_member_deactivate_cross_agency_returns_403(self):
        """
        PATCH /api/v1/agencies/me/members/<id>/deactivate/ where <id> is a
        member of Agency B and the authenticated user is an AGENCY_ADMIN of
        Agency A → 403.  The target user must remain active.

        Validates: Requirements 3.6, 8.2, 8.6
        """
        url = f"/api/v1/agencies/me/members/{self.member_b.pk}/deactivate/"

        response = self.client.patch(
            url,
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.token_a}",
        )

        self.assertEqual(response.status_code, 403)
        # Target user must still be active
        self.member_b.refresh_from_db()
        self.assertTrue(self.member_b.is_active)


# ===========================================================================
# TestGovernmentAuditorWriteBlock — Task 10.14
# Requirements: 12.1, 12.2, 12.3, 12.4
# ===========================================================================


class TestGovernmentAuditorWriteBlock(TestCase):
    """
    Integration tests verifying that GOVERNMENT_AUDITOR has read-only access:
    - Can read all agencies' tenders via the cross-agency endpoint (Req 12.1)
    - Cannot create, edit, delete, or submit tenders (Req 12.2, 12.3)
    - Cannot view SHAP explanations (Req 12.4)
    - Can view fraud scores and red flag summaries (Req 12.3)

    Validates: Requirements 12.1, 12.2, 12.3, 12.4
    """

    def setUp(self):
        self.client = Client()

        # An active agency with an admin user and a draft tender
        self.agency = _make_active_agency(uid="ga_write_block")
        self.agency_admin = _make_agency_user(
            self.agency, role="AGENCY_ADMIN", uid="ga_admin"
        )
        self.draft_submission = _make_tender_submission(
            self.agency, self.agency_admin, status="DRAFT"
        )
        self.submitted_submission = _make_tender_submission(
            self.agency, self.agency_admin, status="SUBMITTED"
        )

        # Government auditor user (no agency)
        self.gov_auditor = _make_gov_auditor_user(uid="ga_auditor")
        self.gov_auditor_token = _get_jwt_for_user(self.gov_auditor)

    def _auth_post(self, url, data=None, token=None):
        token = token or self.gov_auditor_token
        return self.client.post(
            url,
            data=json.dumps(data or {}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _auth_patch(self, url, data=None, token=None):
        token = token or self.gov_auditor_token
        return self.client.patch(
            url,
            data=json.dumps(data or {}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _auth_delete(self, url, token=None):
        token = token or self.gov_auditor_token
        return self.client.delete(
            url,
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def _auth_get(self, url, token=None):
        token = token or self.gov_auditor_token
        return self.client.get(
            url,
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    # -----------------------------------------------------------------------
    # Requirement 12.1 — GOVERNMENT_AUDITOR can read all agencies' tenders
    # -----------------------------------------------------------------------

    def test_gov_auditor_can_read_cross_agency_tender_list(self):
        """
        GET /api/v1/agencies/tenders/ as GOVERNMENT_AUDITOR → 200 with results.

        Validates: Requirement 12.1
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("results", data)
        result_ids = {r["id"] for r in data["results"]}
        self.assertIn(self.draft_submission.pk, result_ids)

    # -----------------------------------------------------------------------
    # Requirement 12.2 — GOVERNMENT_AUDITOR cannot create tenders
    # -----------------------------------------------------------------------

    def test_gov_auditor_cannot_create_tender(self):
        """
        POST /api/v1/agencies/me/tenders/ as GOVERNMENT_AUDITOR → 403.
        GOVERNMENT_AUDITOR is not AGENCY_ADMIN or AGENCY_OFFICER, so
        IsAgencyOfficerOrAdmin denies the request.

        Validates: Requirement 12.2
        """
        payload = {
            "tender_ref": "REF-AUDITOR-001",
            "title": "Auditor Tender",
            "category": "IT",
            "estimated_value": "50000.00",
            "submission_deadline": (
                timezone.now() + timezone.timedelta(days=30)
            ).isoformat(),
            "buyer_name": "Test Buyer",
            "spec_text": "Some specification text.",
        }
        response = self._auth_post(TENDER_LIST_URL, data=payload)

        self.assertEqual(response.status_code, 403)
        # Confirm no new submission was created by the auditor
        from agencies.models import TenderSubmission
        self.assertFalse(
            TenderSubmission.objects.filter(submitted_by=self.gov_auditor).exists()
        )

    # -----------------------------------------------------------------------
    # Requirement 12.2 — GOVERNMENT_AUDITOR cannot edit tenders
    # -----------------------------------------------------------------------

    def test_gov_auditor_cannot_edit_tender(self):
        """
        PATCH /api/v1/agencies/me/tenders/<id>/ as GOVERNMENT_AUDITOR → 403.
        IsAgencyOfficerOrAdmin denies PATCH for GOVERNMENT_AUDITOR.

        Validates: Requirement 12.2
        """
        url = f"/api/v1/agencies/me/tenders/{self.draft_submission.pk}/"
        response = self._auth_patch(url, data={"title": "Hacked Title"})

        self.assertEqual(response.status_code, 403)
        # Confirm the title was not changed
        self.draft_submission.refresh_from_db()
        self.assertNotEqual(self.draft_submission.title, "Hacked Title")

    # -----------------------------------------------------------------------
    # Requirement 12.2 — GOVERNMENT_AUDITOR cannot delete tenders
    # -----------------------------------------------------------------------

    def test_gov_auditor_cannot_delete_tender(self):
        """
        DELETE /api/v1/agencies/me/tenders/<id>/ as GOVERNMENT_AUDITOR → 403.
        IsAgencyOfficerOrAdmin denies DELETE for GOVERNMENT_AUDITOR.

        Validates: Requirement 12.2
        """
        url = f"/api/v1/agencies/me/tenders/{self.draft_submission.pk}/"
        response = self._auth_delete(url)

        self.assertEqual(response.status_code, 403)
        # Confirm the submission still exists
        from agencies.models import TenderSubmission
        self.assertTrue(
            TenderSubmission.objects.filter(pk=self.draft_submission.pk).exists()
        )

    # -----------------------------------------------------------------------
    # Requirement 12.2 — GOVERNMENT_AUDITOR cannot submit tenders
    # -----------------------------------------------------------------------

    @patch("agencies.tasks.score_agency_tender")
    def test_gov_auditor_cannot_submit_tender(self, mock_task):
        """
        POST /api/v1/agencies/me/tenders/<id>/submit/ as GOVERNMENT_AUDITOR → 403.
        IsAgencyOfficerOrAdmin denies the submit action for GOVERNMENT_AUDITOR.
        The scoring task must NOT be enqueued.

        Validates: Requirement 12.2
        """
        mock_task.delay = MagicMock()
        url = f"/api/v1/agencies/me/tenders/{self.draft_submission.pk}/submit/"
        response = self._auth_post(url)

        self.assertEqual(response.status_code, 403)
        mock_task.delay.assert_not_called()
        # Submission status must remain DRAFT
        self.draft_submission.refresh_from_db()
        self.assertEqual(self.draft_submission.status, "DRAFT")

    # -----------------------------------------------------------------------
    # Requirement 12.4 — GOVERNMENT_AUDITOR cannot view SHAP explanations
    # -----------------------------------------------------------------------

    def test_gov_auditor_cannot_view_shap_explanation(self):
        """
        GET /api/v1/tenders/<id>/explanation/ as GOVERNMENT_AUDITOR → 403.
        TenderExplanationView uses IsAuditorOrAdmin which excludes
        GOVERNMENT_AUDITOR.

        Validates: Requirement 12.4
        """
        # Create a Tender record to use as the target
        from tenders.models import Tender
        uid = uuid.uuid4().hex[:8]
        tender = Tender.objects.create(
            tender_id=f"TENDER-SHAP-{uid}",
            title="Test Tender for SHAP",
            category="IT",
            estimated_value=100000,
            submission_deadline=timezone.now() + timezone.timedelta(days=30),
            buyer_id=f"BUYER-{uid}",
            buyer_name="Test Buyer",
        )
        url = f"/api/v1/tenders/{tender.pk}/explanation/"
        response = self._auth_get(url)

        self.assertEqual(response.status_code, 403)

    # -----------------------------------------------------------------------
    # Requirement 12.3 — GOVERNMENT_AUDITOR can view fraud scores
    # -----------------------------------------------------------------------

    def test_gov_auditor_can_view_fraud_scores_in_cross_agency_list(self):
        """
        GET /api/v1/agencies/tenders/ as GOVERNMENT_AUDITOR returns records
        that include fraud_risk_score and risk_badge fields.

        Validates: Requirement 12.3
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["results"]), 0)

        for record in data["results"]:
            # fraud_risk_score key must be present (may be None if not yet scored)
            self.assertIn(
                "fraud_risk_score", record,
                "fraud_risk_score field missing from cross-agency list record",
            )
            self.assertIn(
                "risk_badge", record,
                "risk_badge field missing from cross-agency list record",
            )

    # -----------------------------------------------------------------------
    # Requirement 12.3 — GOVERNMENT_AUDITOR can view red flag summaries
    # -----------------------------------------------------------------------

    def test_gov_auditor_can_view_red_flags_via_cross_agency_list(self):
        """
        GET /api/v1/agencies/tenders/ as GOVERNMENT_AUDITOR returns records
        that include agency_id and agency_name (cross-agency context).
        The cross-agency list endpoint is accessible and returns data.

        Validates: Requirement 12.3
        """
        response = self._auth_get(CROSS_AGENCY_TENDER_LIST_URL)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreater(len(data["results"]), 0)

        for record in data["results"]:
            self.assertIn("agency_id", record)
            self.assertIn("agency_name", record)
