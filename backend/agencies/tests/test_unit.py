"""
Unit tests for TenderSubmission.transition_to()

# Feature: agency-portal-rbac
# Requirements: 7.1, 7.2

Covers:
  - All 6 valid transitions succeed and status is persisted correctly
  - All invalid transitions raise ValueError and leave status unchanged
  - Every status in the state machine is exercised as both source and target
"""

import uuid
from decimal import Decimal

import pytest
from django.test import TestCase
from django.utils import timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_gstin() -> str:
    """Generate a unique GSTIN-like string to avoid DB uniqueness collisions."""
    suffix = uuid.uuid4().hex[:6].upper()
    return f"27AAPFU{suffix[:4]}1Z5"


def _make_agency():
    """Create a minimal Agency in the test DB."""
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


def _make_submission(agency, status="DRAFT"):
    """Create a TenderSubmission with the given status."""
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
        status=status,
    )


# ===========================================================================
# Valid transitions — Requirement 7.1
# DRAFT → SUBMITTED
# SUBMITTED → UNDER_REVIEW
# SUBMITTED → CLEARED
# UNDER_REVIEW → FLAGGED
# UNDER_REVIEW → CLEARED
# FLAGGED → CLEARED
# ===========================================================================

class TestValidTransitions(TestCase):
    """
    All 6 permitted transitions must succeed: status is updated in the DB
    and no exception is raised.

    Validates: Requirement 7.1
    """

    def setUp(self):
        self.agency = _make_agency()

    def test_draft_to_submitted(self):
        """DRAFT → SUBMITTED is a valid transition."""
        submission = _make_submission(self.agency, status="DRAFT")
        submission.transition_to("SUBMITTED")
        submission.refresh_from_db()
        self.assertEqual(submission.status, "SUBMITTED")

    def test_submitted_to_under_review(self):
        """SUBMITTED → UNDER_REVIEW is a valid transition."""
        submission = _make_submission(self.agency, status="SUBMITTED")
        submission.transition_to("UNDER_REVIEW")
        submission.refresh_from_db()
        self.assertEqual(submission.status, "UNDER_REVIEW")

    def test_submitted_to_cleared(self):
        """SUBMITTED → CLEARED is a valid transition."""
        submission = _make_submission(self.agency, status="SUBMITTED")
        submission.transition_to("CLEARED")
        submission.refresh_from_db()
        self.assertEqual(submission.status, "CLEARED")

    def test_under_review_to_flagged(self):
        """UNDER_REVIEW → FLAGGED is a valid transition."""
        submission = _make_submission(self.agency, status="UNDER_REVIEW")
        submission.transition_to("FLAGGED")
        submission.refresh_from_db()
        self.assertEqual(submission.status, "FLAGGED")

    def test_under_review_to_cleared(self):
        """UNDER_REVIEW → CLEARED is a valid transition."""
        submission = _make_submission(self.agency, status="UNDER_REVIEW")
        submission.transition_to("CLEARED")
        submission.refresh_from_db()
        self.assertEqual(submission.status, "CLEARED")

    def test_flagged_to_cleared(self):
        """FLAGGED → CLEARED is a valid transition (after manual review)."""
        submission = _make_submission(self.agency, status="FLAGGED")
        submission.transition_to("CLEARED")
        submission.refresh_from_db()
        self.assertEqual(submission.status, "CLEARED")


# ===========================================================================
# Invalid transitions — Requirement 7.2
# For every status, all non-permitted target statuses must raise ValueError
# and leave the status unchanged in the DB.
# ===========================================================================

class TestInvalidTransitions(TestCase):
    """
    Every transition not in VALID_TRANSITIONS must raise ValueError and
    leave the submission status unchanged in the database.

    Validates: Requirements 7.1, 7.2
    """

    def setUp(self):
        self.agency = _make_agency()

    def _assert_invalid(self, from_status: str, to_status: str):
        """Helper: assert transition raises ValueError and status is unchanged."""
        submission = _make_submission(self.agency, status=from_status)
        with self.assertRaises(ValueError):
            submission.transition_to(to_status)
        submission.refresh_from_db()
        self.assertEqual(
            submission.status,
            from_status,
            msg=(
                f"Status changed after invalid transition attempt "
                f"{from_status!r} → {to_status!r}"
            ),
        )

    # --- DRAFT: only SUBMITTED is valid; all others are invalid ---

    def test_draft_to_draft_is_invalid(self):
        """DRAFT → DRAFT is not a permitted transition."""
        self._assert_invalid("DRAFT", "DRAFT")

    def test_draft_to_under_review_is_invalid(self):
        """DRAFT → UNDER_REVIEW is not a permitted transition."""
        self._assert_invalid("DRAFT", "UNDER_REVIEW")

    def test_draft_to_flagged_is_invalid(self):
        """DRAFT → FLAGGED is not a permitted transition."""
        self._assert_invalid("DRAFT", "FLAGGED")

    def test_draft_to_cleared_is_invalid(self):
        """DRAFT → CLEARED is not a permitted transition."""
        self._assert_invalid("DRAFT", "CLEARED")

    # --- SUBMITTED: only UNDER_REVIEW and CLEARED are valid ---

    def test_submitted_to_draft_is_invalid(self):
        """SUBMITTED → DRAFT is not a permitted transition."""
        self._assert_invalid("SUBMITTED", "DRAFT")

    def test_submitted_to_submitted_is_invalid(self):
        """SUBMITTED → SUBMITTED is not a permitted transition."""
        self._assert_invalid("SUBMITTED", "SUBMITTED")

    def test_submitted_to_flagged_is_invalid(self):
        """SUBMITTED → FLAGGED is not a permitted transition."""
        self._assert_invalid("SUBMITTED", "FLAGGED")

    # --- UNDER_REVIEW: only FLAGGED and CLEARED are valid ---

    def test_under_review_to_draft_is_invalid(self):
        """UNDER_REVIEW → DRAFT is not a permitted transition."""
        self._assert_invalid("UNDER_REVIEW", "DRAFT")

    def test_under_review_to_submitted_is_invalid(self):
        """UNDER_REVIEW → SUBMITTED is not a permitted transition."""
        self._assert_invalid("UNDER_REVIEW", "SUBMITTED")

    def test_under_review_to_under_review_is_invalid(self):
        """UNDER_REVIEW → UNDER_REVIEW is not a permitted transition."""
        self._assert_invalid("UNDER_REVIEW", "UNDER_REVIEW")

    # --- FLAGGED: only CLEARED is valid ---

    def test_flagged_to_draft_is_invalid(self):
        """FLAGGED → DRAFT is not a permitted transition."""
        self._assert_invalid("FLAGGED", "DRAFT")

    def test_flagged_to_submitted_is_invalid(self):
        """FLAGGED → SUBMITTED is not a permitted transition."""
        self._assert_invalid("FLAGGED", "SUBMITTED")

    def test_flagged_to_under_review_is_invalid(self):
        """FLAGGED → UNDER_REVIEW is not a permitted transition."""
        self._assert_invalid("FLAGGED", "UNDER_REVIEW")

    def test_flagged_to_flagged_is_invalid(self):
        """FLAGGED → FLAGGED is not a permitted transition."""
        self._assert_invalid("FLAGGED", "FLAGGED")

    # --- CLEARED: terminal state — no transitions are valid ---

    def test_cleared_to_draft_is_invalid(self):
        """CLEARED → DRAFT is not a permitted transition (terminal state)."""
        self._assert_invalid("CLEARED", "DRAFT")

    def test_cleared_to_submitted_is_invalid(self):
        """CLEARED → SUBMITTED is not a permitted transition (terminal state)."""
        self._assert_invalid("CLEARED", "SUBMITTED")

    def test_cleared_to_under_review_is_invalid(self):
        """CLEARED → UNDER_REVIEW is not a permitted transition (terminal state)."""
        self._assert_invalid("CLEARED", "UNDER_REVIEW")

    def test_cleared_to_flagged_is_invalid(self):
        """CLEARED → FLAGGED is not a permitted transition (terminal state)."""
        self._assert_invalid("CLEARED", "FLAGGED")

    def test_cleared_to_cleared_is_invalid(self):
        """CLEARED → CLEARED is not a permitted transition (terminal state)."""
        self._assert_invalid("CLEARED", "CLEARED")


# ===========================================================================
# ValueError message content — Requirement 7.2
# The error message must identify the invalid transition.
# ===========================================================================

class TestInvalidTransitionErrorMessage(TestCase):
    """
    The ValueError raised for an invalid transition must include both the
    current status and the attempted target status in its message.

    Validates: Requirement 7.2
    """

    def setUp(self):
        self.agency = _make_agency()

    def test_error_message_identifies_transition(self):
        """ValueError message must name the invalid transition."""
        submission = _make_submission(self.agency, status="DRAFT")
        with self.assertRaises(ValueError) as ctx:
            submission.transition_to("FLAGGED")
        message = str(ctx.exception)
        self.assertIn("DRAFT", message)
        self.assertIn("FLAGGED", message)

    def test_error_message_for_cleared_terminal_state(self):
        """ValueError from CLEARED (terminal) must name both statuses."""
        submission = _make_submission(self.agency, status="CLEARED")
        with self.assertRaises(ValueError) as ctx:
            submission.transition_to("DRAFT")
        message = str(ctx.exception)
        self.assertIn("CLEARED", message)
        self.assertIn("DRAFT", message)


# ===========================================================================
# Invitation.is_valid — Requirement 4.5
# An invitation is valid only when consumed_at is None AND expires_at > now().
# ===========================================================================

def _make_user(username=None):
    """Create a minimal User in the test DB."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    uid = uuid.uuid4().hex[:8]
    username = username or f"user_{uid}"
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="testpass123",
    )


def _make_invitation(agency, user, expires_at, consumed_at=None):
    """Create a minimal Invitation in the test DB."""
    from agencies.models import Invitation
    token_hash = uuid.uuid4().hex  # unique 32-char hex, good enough for tests
    return Invitation.objects.create(
        token_hash=token_hash,
        email=f"invitee-{uuid.uuid4().hex[:6]}@example.com",
        role="AGENCY_OFFICER",
        agency=agency,
        invited_by=user,
        expires_at=expires_at,
        consumed_at=consumed_at,
    )


class TestInvitationIsValid(TestCase):
    """
    Unit tests for the Invitation.is_valid property.

    is_valid returns True only when:
      - consumed_at is None, AND
      - expires_at > timezone.now()

    Validates: Requirement 4.5
    """

    def setUp(self):
        self.agency = _make_agency()
        self.user = _make_user()

    def test_valid_invitation_returns_true(self):
        """A non-expired, non-consumed invitation must be valid."""
        future = timezone.now() + timezone.timedelta(hours=24)
        invitation = _make_invitation(self.agency, self.user, expires_at=future)
        self.assertTrue(invitation.is_valid)

    def test_expired_invitation_returns_false(self):
        """An invitation whose expires_at is in the past must not be valid."""
        past = timezone.now() - timezone.timedelta(seconds=1)
        invitation = _make_invitation(self.agency, self.user, expires_at=past)
        self.assertFalse(invitation.is_valid)

    def test_consumed_invitation_returns_false(self):
        """An invitation with consumed_at set must not be valid, even if not expired."""
        future = timezone.now() + timezone.timedelta(hours=24)
        consumed_time = timezone.now() - timezone.timedelta(minutes=5)
        invitation = _make_invitation(
            self.agency, self.user,
            expires_at=future,
            consumed_at=consumed_time,
        )
        self.assertFalse(invitation.is_valid)

    def test_expired_and_consumed_invitation_returns_false(self):
        """An invitation that is both expired and consumed must not be valid."""
        past_expires = timezone.now() - timezone.timedelta(hours=1)
        consumed_time = timezone.now() - timezone.timedelta(hours=2)
        invitation = _make_invitation(
            self.agency, self.user,
            expires_at=past_expires,
            consumed_at=consumed_time,
        )
        self.assertFalse(invitation.is_valid)

    def test_invitation_expiring_exactly_now_returns_false(self):
        """
        An invitation whose expires_at equals (or is just behind) now must not be valid.
        is_valid uses strict greater-than, so expires_at == now() is invalid.
        """
        # Set expires_at slightly in the past to simulate the boundary condition
        # where the clock has just ticked past the expiry moment.
        boundary = timezone.now() - timezone.timedelta(microseconds=1)
        invitation = _make_invitation(self.agency, self.user, expires_at=boundary)
        self.assertFalse(invitation.is_valid)
