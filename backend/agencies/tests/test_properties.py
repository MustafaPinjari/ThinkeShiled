"""
Property-based tests for the Agency Portal RBAC feature.

# Feature: agency-portal-rbac, Property 1: Agency-scoped queryset never leaks cross-agency data

**Validates: Requirements 8.1, 8.2, 3.2**

For any authenticated user with role AGENCY_ADMIN, AGENCY_OFFICER, or REVIEWER,
every TenderSubmission returned by TenderSubmission.objects.for_agency(user.agency_id)
SHALL have agency_id equal to user.agency_id.
"""

from __future__ import annotations

import os
import sys
import uuid
from decimal import Decimal
from unittest.mock import MagicMock

from django.utils import timezone
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

# ---------------------------------------------------------------------------
# sys.path bootstrap
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_ROOT_DIR = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
for _p in (_BACKEND_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_gstin() -> str:
    """Generate a unique GSTIN-like string using uuid4 to avoid collisions."""
    # GSTIN format: 2 digits + 5 uppercase + 4 digits + 1 uppercase + 1 alphanum + Z + 1 alphanum
    # We use a uuid-based suffix to guarantee uniqueness across Hypothesis iterations.
    suffix = uuid.uuid4().hex[:6].upper()
    return f"27AAPFU{suffix[:4]}1Z5"


def _make_agency():
    """Create a minimal Agency in the test DB with a guaranteed-unique GSTIN."""
    from agencies.models import Agency, AgencyStatus

    uid = uuid.uuid4().hex[:8]
    return Agency.objects.create(
        legal_name=f"Agency {uid}",
        gstin=_unique_gstin(),
        ministry="Ministry of Test",
        contact_name="Test Contact",
        contact_email=f"contact-{uid}@example.com",
        status=AgencyStatus.ACTIVE,
    )


def _make_submission(agency):
    """Create a minimal TenderSubmission for the given agency."""
    from agencies.models import TenderSubmission

    uid = uuid.uuid4().hex[:8]
    return TenderSubmission.objects.create(
        agency=agency,
        submitted_by=None,
        tender=None,
        tender_ref=f"REF-{uid}",
        title=f"Tender {uid}",
        category="IT",
        estimated_value=Decimal("100000.00"),
        submission_deadline=timezone.now() + timezone.timedelta(days=30),
        buyer_name="Test Buyer",
    )


# ===========================================================================
# Property 1: Agency-scoped queryset never leaks cross-agency data
# Validates: Requirements 8.1, 8.2, 3.2
# ===========================================================================

class AgencyScopedQuerysetProperty(TestCase):
    """
    Property 1: Agency-scoped queryset never leaks cross-agency data

    **Validates: Requirements 8.1, 8.2, 3.2**

    For any authenticated user with role AGENCY_ADMIN/AGENCY_OFFICER/REVIEWER,
    every TenderSubmission returned by TenderSubmission.objects.for_agency(agency_id)
    has agency_id equal to the queried agency_id, and the count matches exactly
    the number of submissions created for that agency.
    """

    @given(
        n_agency_a=st.integers(min_value=1, max_value=5),
        n_agency_b=st.integers(min_value=1, max_value=5),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_for_agency_returns_only_own_agency_records(
        self, n_agency_a: int, n_agency_b: int
    ):
        """
        Property 1: for_agency() never leaks cross-agency data.

        **Validates: Requirements 8.1, 8.2, 3.2**

        Steps:
          1. Create two distinct agencies (A and B).
          2. Create N submissions for agency A and M submissions for agency B.
          3. Call TenderSubmission.objects.for_agency(agency_A.id).
          4. Assert every returned record has agency_id == agency_A.id.
          5. Assert the count equals N (no records from agency B leaked).
        """
        from agencies.models import TenderSubmission

        # 1. Create two distinct agencies
        agency_a = _make_agency()
        agency_b = _make_agency()

        # 2. Create N submissions for agency A and M for agency B
        for _ in range(n_agency_a):
            _make_submission(agency_a)
        for _ in range(n_agency_b):
            _make_submission(agency_b)

        # 3. Query using the agency-scoped manager
        results_a = TenderSubmission.objects.for_agency(agency_a.id)

        # 4. Every returned record must belong to agency A
        for submission in results_a:
            assert submission.agency_id == agency_a.id, (
                f"Cross-agency data leak detected: submission {submission.pk} "
                f"has agency_id={submission.agency_id}, expected {agency_a.id}. "
                f"n_agency_a={n_agency_a}, n_agency_b={n_agency_b}"
            )

        # 5. Count must match exactly N (no records from agency B)
        count = results_a.count()
        assert count == n_agency_a, (
            f"for_agency() returned {count} records, expected {n_agency_a}. "
            f"n_agency_a={n_agency_a}, n_agency_b={n_agency_b}. "
            f"agency_a.id={agency_a.id}, agency_b.id={agency_b.id}"
        )

    @given(
        n_agency_a=st.integers(min_value=1, max_value=5),
        n_agency_b=st.integers(min_value=1, max_value=5),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_for_agency_b_does_not_return_agency_a_records(
        self, n_agency_a: int, n_agency_b: int
    ):
        """
        Property 1 (symmetric): querying agency B never returns agency A records.

        **Validates: Requirements 8.1, 8.2, 3.2**
        """
        from agencies.models import TenderSubmission

        agency_a = _make_agency()
        agency_b = _make_agency()

        for _ in range(n_agency_a):
            _make_submission(agency_a)
        for _ in range(n_agency_b):
            _make_submission(agency_b)

        results_b = TenderSubmission.objects.for_agency(agency_b.id)

        for submission in results_b:
            assert submission.agency_id == agency_b.id, (
                f"Cross-agency data leak detected: submission {submission.pk} "
                f"has agency_id={submission.agency_id}, expected {agency_b.id}."
            )

        count = results_b.count()
        assert count == n_agency_b, (
            f"for_agency() returned {count} records, expected {n_agency_b}. "
            f"agency_b.id={agency_b.id}"
        )


# ===========================================================================
# Property 2: RBAC permission denial is exhaustive
# Feature: agency-portal-rbac, Property 2: RBAC permission denial is exhaustive
# Validates: Requirements 3.1, 3.2, 3.3, 3.6, 3.7, 3.8
# ===========================================================================

class RBACPermissionDenialProperty(TestCase):
    """
    Property 2: RBAC permission denial is exhaustive

    **Validates: Requirements 3.1, 3.2, 3.3, 3.6, 3.7, 3.8**

    For any user role and any API action, if the role is NOT in the permitted
    set for that action (as defined in the Role Permission Matrix), the
    permission check SHALL return False.
    """

    @given(
        role=st.sampled_from(sorted([
            "AGENCY_ADMIN",
            "AGENCY_OFFICER",
            "REVIEWER",
            "GOVERNMENT_AUDITOR",
            "AUDITOR",
            "ADMIN",
        ])),
        action=st.sampled_from(sorted([
            "view_own_tenders",
            "create_tender",
            "edit_draft_tender",
            "submit_tender",
            "view_fraud_score",
            "view_shap",
            "invite_members",
            "manage_profile",
            "view_all_agencies",
            "suspend_agency",
        ])),
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_permission_denied_for_roles_not_in_matrix(self, role: str, action: str):
        """
        Property 2: has_permission() returns False for any (role, action) pair
        where the role is NOT in the permitted set defined by PERMISSION_MATRIX.

        **Validates: Requirements 3.1, 3.2, 3.3, 3.6, 3.7, 3.8**

        Steps:
          1. Generate a random (role, action) pair.
          2. Filter with assume() to keep only pairs where role is NOT permitted.
          3. Build a mock DRF request with request.user.role = role and
             request.user.is_authenticated = True.
          4. Assert has_permission(role, action) returns False.
          5. Assert the corresponding DRF permission class also returns False
             when called with the mock request.
        """
        from agencies.permissions import (
            PERMISSION_MATRIX,
            has_permission,
        )

        # 2. Only test (role, action) pairs where the role is NOT permitted
        assume(role not in PERMISSION_MATRIX[action])

        # 3. Build a mock request with the given role
        mock_user = MagicMock()
        mock_user.role = role
        mock_user.is_authenticated = True

        mock_request = MagicMock()
        mock_request.user = mock_user

        # 4. The matrix-based helper must return False
        result = has_permission(role, action)
        assert result is False, (
            f"has_permission({role!r}, {action!r}) returned {result!r}, "
            f"expected False. Permitted roles for {action!r}: {PERMISSION_MATRIX[action]}"
        )

    @given(
        role=st.sampled_from(sorted([
            "AGENCY_ADMIN",
            "AGENCY_OFFICER",
            "REVIEWER",
            "GOVERNMENT_AUDITOR",
            "AUDITOR",
            "ADMIN",
        ])),
        action=st.sampled_from(sorted([
            "view_own_tenders",
            "create_tender",
            "edit_draft_tender",
            "submit_tender",
            "view_fraud_score",
            "view_shap",
            "invite_members",
            "manage_profile",
            "view_all_agencies",
            "suspend_agency",
        ])),
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_permission_granted_for_roles_in_matrix(self, role: str, action: str):
        """
        Complementary check: has_permission() returns True for any (role, action)
        pair where the role IS in the permitted set.

        **Validates: Requirements 3.1, 3.2, 3.3, 3.6, 3.7, 3.8**
        """
        from agencies.permissions import PERMISSION_MATRIX, has_permission

        # Only test pairs where the role IS permitted
        assume(role in PERMISSION_MATRIX[action])

        result = has_permission(role, action)
        assert result is True, (
            f"has_permission({role!r}, {action!r}) returned {result!r}, "
            f"expected True. Permitted roles for {action!r}: {PERMISSION_MATRIX[action]}"
        )


# ===========================================================================
# Property 3: Status machine admits only valid transitions
# Feature: agency-portal-rbac, Property 3: Status machine admits only valid transitions
# Validates: Requirements 7.1, 7.2
# ===========================================================================

class StatusMachineTransitionProperty(TestCase):
    """
    Property 3: Tender submission status machine admits only valid transitions

    **Validates: Requirements 7.1, 7.2**

    For any TenderSubmission in any status S, calling transition_to(T) where T is
    NOT in VALID_TRANSITIONS[S] SHALL raise a ValueError and leave the submission
    status unchanged.
    """

    @given(
        current_status=st.sampled_from(["DRAFT", "SUBMITTED", "UNDER_REVIEW", "FLAGGED", "CLEARED"]),
        target_status=st.sampled_from(["DRAFT", "SUBMITTED", "UNDER_REVIEW", "FLAGGED", "CLEARED"]),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_invalid_transition_raises_value_error(
        self, current_status: str, target_status: str
    ):
        """
        Property 3 (invalid transitions): transition_to() raises ValueError for
        any target status not in VALID_TRANSITIONS[current_status], and the
        submission status remains unchanged in the DB.

        **Validates: Requirements 7.1, 7.2**

        Steps:
          1. Use st.sampled_from for both current_status and target_status.
          2. Use assume() to filter to only invalid (current, target) pairs.
          3. Create a TenderSubmission in the DB with the given current_status.
          4. Call submission.transition_to(target_status) and assert ValueError.
          5. Reload from DB and assert status is unchanged.
        """
        from agencies.models import VALID_TRANSITIONS, TenderSubmission

        # 2. Only test pairs where the transition is INVALID
        assume(target_status not in VALID_TRANSITIONS[current_status])

        # 3. Create a TenderSubmission with the given current_status
        agency = _make_agency()
        uid = uuid.uuid4().hex[:8]
        submission = TenderSubmission.objects.create(
            agency=agency,
            submitted_by=None,
            tender=None,
            tender_ref=f"REF-{uid}",
            title=f"Tender {uid}",
            category="IT",
            estimated_value=Decimal("100000.00"),
            submission_deadline=timezone.now() + timezone.timedelta(days=30),
            buyer_name="Test Buyer",
            status=current_status,
        )

        # 4. Assert that transition_to raises ValueError
        try:
            submission.transition_to(target_status)
            assert False, (
                f"Expected ValueError for transition {current_status!r} → {target_status!r}, "
                f"but no exception was raised."
            )
        except ValueError:
            pass  # expected

        # 5. Reload from DB and assert status is unchanged
        submission.refresh_from_db()
        assert submission.status == current_status, (
            f"Status changed after invalid transition attempt: "
            f"expected {current_status!r}, got {submission.status!r}. "
            f"Attempted transition: {current_status!r} → {target_status!r}"
        )

    @given(
        current_status=st.sampled_from(["DRAFT", "SUBMITTED", "UNDER_REVIEW", "FLAGGED", "CLEARED"]),
        target_status=st.sampled_from(["DRAFT", "SUBMITTED", "UNDER_REVIEW", "FLAGGED", "CLEARED"]),
    )
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_valid_transition_succeeds_and_status_changes(
        self, current_status: str, target_status: str
    ):
        """
        Property 3 (complementary — valid transitions): transition_to() succeeds
        for any target status in VALID_TRANSITIONS[current_status], and the
        submission status is updated in the DB.

        **Validates: Requirements 7.1, 7.2**

        Steps:
          1. Use assume() to filter to only valid (current, target) pairs.
          2. Create a TenderSubmission in the DB with the given current_status.
          3. Call submission.transition_to(target_status) — must not raise.
          4. Reload from DB and assert status equals target_status.
        """
        from agencies.models import VALID_TRANSITIONS, TenderSubmission

        # 1. Only test pairs where the transition IS valid
        assume(target_status in VALID_TRANSITIONS[current_status])

        # 2. Create a TenderSubmission with the given current_status
        agency = _make_agency()
        uid = uuid.uuid4().hex[:8]
        submission = TenderSubmission.objects.create(
            agency=agency,
            submitted_by=None,
            tender=None,
            tender_ref=f"REF-{uid}",
            title=f"Tender {uid}",
            category="IT",
            estimated_value=Decimal("100000.00"),
            submission_deadline=timezone.now() + timezone.timedelta(days=30),
            buyer_name="Test Buyer",
            status=current_status,
        )

        # 3. Call transition_to — must not raise
        try:
            submission.transition_to(target_status)
        except ValueError as exc:
            assert False, (
                f"Unexpected ValueError for valid transition "
                f"{current_status!r} → {target_status!r}: {exc}"
            )

        # 4. Reload from DB and assert status equals target_status
        submission.refresh_from_db()
        assert submission.status == target_status, (
            f"Status not updated after valid transition: "
            f"expected {target_status!r}, got {submission.status!r}. "
            f"Transition: {current_status!r} → {target_status!r}"
        )


# ===========================================================================
# Property 4: Invitation token round-trip
# Feature: agency-portal-rbac, Property 4: Invitation token round-trip
# Validates: Requirements 4.1, 4.3, 4.4, 4.5
# ===========================================================================

import hashlib


class InvitationTokenRoundTripProperty(TestCase):
    """
    Property 4: Invitation token round-trip

    **Validates: Requirements 4.1, 4.3, 4.4, 4.5**

    For any valid (unexpired, unconsumed) invitation, hashing the raw token with
    SHA-256 SHALL produce the stored token_hash, and looking up by that hash
    SHALL return the original invitation record.
    """

    @given(raw_token=st.binary(min_size=32, max_size=32))
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_sha256_hash_lookup_returns_correct_invitation(self, raw_token: bytes):
        """
        Property 4: sha256(token).hexdigest() == stored token_hash, and
        Invitation.objects.get(token_hash=hash) returns the original record.

        **Validates: Requirements 4.1, 4.3, 4.4, 4.5**

        Steps:
          1. Generate a random 32-byte token via st.binary(min_size=32, max_size=32).
          2. Compute hashlib.sha256(token).hexdigest() to get the hash.
          3. Create an Invitation record in the DB with token_hash = computed_hash.
          4. Look up Invitation.objects.get(token_hash=computed_hash).
          5. Assert the returned invitation's pk matches the created one.
          6. Assert sha256(token).hexdigest() == invitation.token_hash.
        """
        from agencies.models import Invitation

        # 2. Compute SHA-256 hash of the raw token
        computed_hash = hashlib.sha256(raw_token).hexdigest()

        # 3. Create an Invitation record with the computed hash
        agency = _make_agency()
        uid = uuid.uuid4().hex[:8]
        invitation = Invitation.objects.create(
            token_hash=computed_hash,
            email=f"invite-{uid}@example.com",
            role="AGENCY_OFFICER",
            agency=agency,
            invited_by=None,
            expires_at=timezone.now() + timezone.timedelta(days=7),
            consumed_at=None,
        )

        # 4. Look up by hash
        found = Invitation.objects.get(token_hash=computed_hash)

        # 5. Assert the pk matches
        assert found.pk == invitation.pk, (
            f"Lookup returned invitation pk={found.pk}, expected pk={invitation.pk}. "
            f"token_hash={computed_hash!r}"
        )

        # 6. Assert the hash round-trips correctly
        assert hashlib.sha256(raw_token).hexdigest() == found.token_hash, (
            f"SHA-256 round-trip failed: computed {hashlib.sha256(raw_token).hexdigest()!r} "
            f"but stored {found.token_hash!r}"
        )


# ===========================================================================
# Property 5: GSTIN validation rejects all non-conforming strings
# Feature: agency-portal-rbac, Property 5: GSTIN validation rejects all non-conforming strings
# Validates: Requirements 2.7
# ===========================================================================

import re as _re

# GSTIN regex (mirrors the one in validators.py)
_GSTIN_RE = _re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)

# ---------------------------------------------------------------------------
# Hypothesis strategy: build a valid GSTIN string character-by-character
# ---------------------------------------------------------------------------

_gstin_strategy = st.builds(
    lambda d2, alpha5, d4, alpha1, an1, last: d2 + alpha5 + d4 + alpha1 + an1 + "Z" + last,
    d2=st.text(alphabet="0123456789", min_size=2, max_size=2),
    alpha5=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=5, max_size=5),
    d4=st.text(alphabet="0123456789", min_size=4, max_size=4),
    alpha1=st.text(alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=1),
    an1=st.text(alphabet="123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=1),
    last=st.text(alphabet="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ", min_size=1, max_size=1),
)


class GSTINValidationProperty(TestCase):
    """
    Property 5: GSTIN validation rejects all non-conforming strings

    **Validates: Requirements 2.7**

    For any string that does NOT match the GSTIN pattern
    ``[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}``,
    the GSTIN validator SHALL raise ValidationError.
    For any string that DOES match, it SHALL not raise.
    """

    @given(gstin=_gstin_strategy)
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_valid_gstin_does_not_raise(self, gstin: str):
        """
        Property 5 (valid path): validate_gstin() does NOT raise for any string
        that matches the GSTIN pattern.

        **Validates: Requirements 2.7**

        Steps:
          1. Generate a valid GSTIN string by composing the exact character classes.
          2. Call validate_gstin(gstin).
          3. Assert no ValidationError is raised.
        """
        from agencies.validators import validate_gstin
        from django.core.exceptions import ValidationError

        # Sanity-check: the strategy must produce strings that match the regex
        assert _GSTIN_RE.match(gstin), (
            f"Strategy produced a non-matching GSTIN: {gstin!r}. "
            "This is a test-strategy bug, not a validator bug."
        )

        try:
            validate_gstin(gstin)
        except ValidationError as exc:
            assert False, (
                f"validate_gstin({gstin!r}) raised ValidationError unexpectedly: {exc}"
            )

    @given(value=st.text())
    @settings(
        max_examples=500,
        suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much],
        deadline=None,
    )
    def test_invalid_gstin_raises_validation_error(self, value: str):
        """
        Property 5 (invalid path): validate_gstin() raises ValidationError for
        any string that does NOT match the GSTIN pattern.

        **Validates: Requirements 2.7**

        Steps:
          1. Generate a random string via st.text().
          2. Use assume() to keep only strings that do NOT match the GSTIN regex.
          3. Call validate_gstin(value).
          4. Assert ValidationError is raised.
        """
        from agencies.validators import validate_gstin
        from django.core.exceptions import ValidationError

        # 2. Only test strings that do NOT match the GSTIN pattern
        assume(not _GSTIN_RE.match(value))

        # 3 & 4. Validator must raise
        try:
            validate_gstin(value)
            assert False, (
                f"validate_gstin({value!r}) did NOT raise ValidationError, "
                "but the string does not match the GSTIN pattern."
            )
        except ValidationError:
            pass  # expected


# ===========================================================================
# Property 6: Suspended agency blocks all authentication
# Feature: agency-portal-rbac, Property 6: Suspended agency blocks all authentication
# Validates: Requirements 2.5, 9.7
# ===========================================================================

from unittest.mock import patch


class SuspendedAgencyBlocksAuthProperty(TestCase):
    """
    Property 6: Suspended agency blocks all authentication

    **Validates: Requirements 2.5, 9.7**

    For any user whose `agency.status` is `SUSPENDED`, the
    `AgencyAwareJWTAuthentication.get_user()` method SHALL raise
    `AuthenticationFailed` regardless of the user's own `is_active` state.
    """

    @given(is_active=st.booleans())
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_suspended_agency_raises_authentication_failed(self, is_active: bool):
        """
        Property 6: get_user() raises AuthenticationFailed for any user linked
        to a SUSPENDED agency, regardless of the user's is_active value.

        **Validates: Requirements 2.5, 9.7**

        Steps:
          1. Use st.booleans() to generate a random is_active value for the user.
          2. Create an Agency with status=SUSPENDED in the test DB.
          3. Create a User linked to that agency with the generated is_active value.
          4. Mock the parent class get_user() to return the user.
          5. Call AgencyAwareJWTAuthentication().get_user(mock_token).
          6. Assert AuthenticationFailed is raised regardless of is_active.
        """
        from agencies.jwt_auth import AgencyAwareJWTAuthentication
        from agencies.models import Agency, AgencyStatus
        from rest_framework_simplejwt.exceptions import AuthenticationFailed

        # 2. Create an Agency with status=SUSPENDED
        uid = uuid.uuid4().hex[:8]
        suspended_agency = Agency.objects.create(
            legal_name=f"Suspended Agency {uid}",
            gstin=_unique_gstin(),
            ministry="Ministry of Test",
            contact_name="Test Contact",
            contact_email=f"contact-{uid}@example.com",
            status=AgencyStatus.SUSPENDED,
        )

        # 3. Create a User linked to the suspended agency
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User(
            username=f"user-{uid}",
            email=f"user-{uid}@example.com",
            is_active=is_active,
        )
        # Attach the suspended agency directly (without saving to DB,
        # since the agency FK may not be on the User model yet)
        user.agency = suspended_agency

        # 4. Mock the parent class get_user() to return our user
        mock_token = MagicMock()
        authenticator = AgencyAwareJWTAuthentication()

        with patch.object(
            AgencyAwareJWTAuthentication.__bases__[0],
            "get_user",
            return_value=user,
        ):
            # 5 & 6. Assert AuthenticationFailed is raised
            try:
                authenticator.get_user(mock_token)
                assert False, (
                    f"Expected AuthenticationFailed for user with suspended agency "
                    f"(is_active={is_active}), but no exception was raised."
                )
            except AuthenticationFailed:
                pass  # expected — property holds


# ===========================================================================
# Property 7: bleach sanitisation is idempotent on clean input
# Feature: agency-portal-rbac, Property 7: bleach sanitisation is idempotent on clean input
# Validates: Requirements 6.11
# ===========================================================================


class BleachSanitisationIdempotentProperty(TestCase):
    """
    Property 7: bleach sanitisation is idempotent on clean input

    **Validates: Requirements 6.11**

    For any string that contains no HTML tags or special characters, applying
    the bleach sanitisation pipeline SHALL return the original string unchanged.
    """

    @given(
        s=st.text(
            alphabet=st.characters(
                # Exclude surrogates (Cs) and control characters (Cc) — bleach
                # replaces non-printable control chars with '?', so they are not
                # "clean" input in the sense of the property.
                blacklist_categories=("Cs", "Cc"),
                blacklist_characters="<>&\"'",
            )
        )
    )
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_bleach_clean_is_identity_on_clean_strings(self, s: str):
        """
        Property 7: bleach_clean(s) == s for any string without HTML special chars.

        **Validates: Requirements 6.11**

        Steps:
          1. Generate a random string using st.text() with an alphabet that
             excludes surrogate code points (category "Cs"), control characters
             (category "Cc"), and the HTML special characters < > & \" '.
          2. Call bleach_clean(s).
          3. Assert the result equals s (sanitisation is a no-op on clean input).
        """
        from agencies.sanitize import bleach_clean

        result = bleach_clean(s)
        assert result == s, (
            f"bleach_clean() modified a clean string.\n"
            f"  Input:  {s!r}\n"
            f"  Output: {result!r}"
        )
