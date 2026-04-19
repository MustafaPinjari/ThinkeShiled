"""
agencies/models.py

All new models for the Agency Portal RBAC feature live here.
The existing tenders app and its Tender model are NOT modified by this feature.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# Agency
# ---------------------------------------------------------------------------

class AgencyStatus(models.TextChoices):
    PENDING_APPROVAL = "PENDING_APPROVAL", "Pending Approval"
    ACTIVE = "ACTIVE", "Active"
    SUSPENDED = "SUSPENDED", "Suspended"


class Agency(models.Model):
    agency_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    legal_name = models.CharField(max_length=500)
    gstin = models.CharField(max_length=15, unique=True)  # immutable after creation
    ministry = models.CharField(max_length=500)
    contact_name = models.CharField(max_length=255)
    contact_email = models.EmailField()
    status = models.CharField(
        max_length=20,
        choices=AgencyStatus.choices,
        default=AgencyStatus.PENDING_APPROVAL,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "agencies_agency"

    def __str__(self):
        return f"{self.legal_name} ({self.gstin})"


# ---------------------------------------------------------------------------
# Invitation
# ---------------------------------------------------------------------------

class Invitation(models.Model):
    token_hash = models.CharField(max_length=64, unique=True)  # SHA-256 hex of raw token
    email = models.EmailField()
    role = models.CharField(max_length=20)  # AGENCY_OFFICER | REVIEWER
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="invitations")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_invitations",
    )
    expires_at = models.DateTimeField()
    consumed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "agencies_invitation"

    @property
    def is_valid(self):
        return self.consumed_at is None and self.expires_at > timezone.now()

    def __str__(self):
        return f"Invitation({self.email} → {self.role} @ {self.agency_id})"


# ---------------------------------------------------------------------------
# EmailVerificationToken
# ---------------------------------------------------------------------------

class EmailVerificationToken(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification_token",
    )
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    # Set to True when all email delivery retries have been exhausted (Requirement 1.8)
    delivery_failed = models.BooleanField(default=False)

    class Meta:
        db_table = "agencies_emailverificationtoken"


# ---------------------------------------------------------------------------
# TenderSubmission
# ---------------------------------------------------------------------------

class SubmissionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    SUBMITTED = "SUBMITTED", "Submitted"
    UNDER_REVIEW = "UNDER_REVIEW", "Under Review"
    FLAGGED = "FLAGGED", "Flagged"
    CLEARED = "CLEARED", "Cleared"


VALID_TRANSITIONS = {
    SubmissionStatus.DRAFT: {SubmissionStatus.SUBMITTED},
    SubmissionStatus.SUBMITTED: {SubmissionStatus.UNDER_REVIEW, SubmissionStatus.CLEARED},
    SubmissionStatus.UNDER_REVIEW: {SubmissionStatus.FLAGGED, SubmissionStatus.CLEARED},
    SubmissionStatus.FLAGGED: {SubmissionStatus.CLEARED},
    SubmissionStatus.CLEARED: set(),
}


class AgencyScopedManager(models.Manager):
    """
    Default manager that filters by agency when a request context is provided.
    Usage: TenderSubmission.objects.for_agency(agency_id)
    """

    def for_agency(self, agency_id):
        return self.get_queryset().filter(agency_id=agency_id)


class TenderSubmission(models.Model):
    agency = models.ForeignKey(Agency, on_delete=models.CASCADE, related_name="submissions")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="submissions",
    )

    # Isolation contract (Requirement 10.8):
    # This field links to the existing tenders.Tender model via a nullable OneToOneField.
    # The Tender model itself is NOT modified by this feature — no new fields, no schema
    # changes, no altered behaviour. The fraud detection pipeline (score_tender, rule engine,
    # ML scoring) continues to operate directly on tenders.Tender using its primary key,
    # completely unaware of TenderSubmission. TenderSubmission is a wrapper that is created
    # only when a portal submission is promoted to SUBMITTED status; until then, tender=None.
    # This preserves the existing pipeline's data contract as required by Requirement 10.8.
    tender = models.OneToOneField(
        "tenders.Tender",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="submission",
    )

    # Submission form fields (pre-pipeline)
    tender_ref = models.CharField(max_length=255)
    title = models.CharField(max_length=500)
    category = models.CharField(max_length=255)
    estimated_value = models.DecimalField(max_digits=20, decimal_places=2)
    submission_deadline = models.DateTimeField()
    publication_date = models.DateTimeField(null=True, blank=True)
    buyer_name = models.CharField(max_length=500)
    spec_text = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.DRAFT,
    )
    review_note = models.TextField(blank=True, default="")  # required when clearing FLAGGED
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AgencyScopedManager()

    class Meta:
        db_table = "agencies_tendersubmission"
        indexes = [
            models.Index(fields=["agency", "status"]),
            models.Index(fields=["agency", "created_at"]),
        ]

    def transition_to(self, new_status, actor=None, review_note=""):
        """
        Transition this submission to a new status.

        Raises ValueError for any transition not in VALID_TRANSITIONS.
        Writes an AuditLog entry on every successful transition.
        """
        if new_status not in VALID_TRANSITIONS.get(self.status, set()):
            raise ValueError(f"Invalid transition: {self.status} → {new_status}")

        old_status = self.status
        self.status = new_status
        if review_note:
            self.review_note = review_note
        self.save(update_fields=["status", "review_note", "updated_at"])

        # Lazy import to avoid circular dependency with audit app
        from audit.models import AuditLog, EventType  # noqa: PLC0415

        AuditLog.objects.create(
            event_type=EventType.STATUS_CHANGED,
            user=actor,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(self.pk),
            data_snapshot={
                "previous_status": old_status,
                "new_status": new_status,
                "agency_id": str(self.agency_id),
            },
        )

    def __str__(self):
        return f"TenderSubmission({self.tender_ref}, {self.status})"
