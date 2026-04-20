"""
agencies/apps.py

App configuration for the agencies app.

The ready() method connects the RedFlag post_save signal handler that
triggers the UNDER_REVIEW → FLAGGED transition and dispatches the
Agency_Admin notification email (Requirement 7.4).
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class AgenciesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "agencies"

    def ready(self):
        """Connect signal handlers when the app is fully loaded."""
        # Import here to avoid circular imports at module load time
        from django.db.models.signals import post_save  # noqa: PLC0415

        from detection.models import RedFlag  # noqa: PLC0415

        post_save.connect(
            _on_red_flag_created,
            sender=RedFlag,
            dispatch_uid="agencies.on_red_flag_created",
        )
        logger.debug("agencies: RedFlag post_save signal connected.")


def _on_red_flag_created(sender, instance, created, **kwargs):
    """
    Signal handler: fires after a RedFlag is saved.

    When a new RedFlag is created for a Tender that has a linked
    TenderSubmission in UNDER_REVIEW status, this handler:
      1. Calls submission.transition_to(FLAGGED) via transition_to().
      2. Enqueues notify_agency_admin_flagged with a countdown ≤ 5 minutes
         so the Agency_Admin email is dispatched within the SLA.
      3. Writes an AuditLog entry for the RED_FLAG_RAISED event.

    Requirements: 7.4
    """
    if not created:
        # Only act on newly created RedFlag records, not updates
        return

    tender = instance.tender

    # Check whether this Tender has a linked TenderSubmission in UNDER_REVIEW
    try:
        submission = tender.submission  # reverse OneToOneField from TenderSubmission
    except Exception:
        # No linked TenderSubmission — this is a non-portal tender; skip
        return

    if submission is None:
        return

    from agencies.models import SubmissionStatus  # noqa: PLC0415

    if submission.status != SubmissionStatus.UNDER_REVIEW:
        # Only transition from UNDER_REVIEW → FLAGGED
        return

    # Perform the status transition
    try:
        submission.transition_to(SubmissionStatus.FLAGGED, actor=None)
        logger.info(
            "agencies: TenderSubmission pk=%d transitioned to FLAGGED "
            "due to RedFlag pk=%d on Tender pk=%d.",
            submission.pk,
            instance.pk,
            tender.pk,
        )
    except ValueError as ve:
        logger.warning(
            "agencies: Could not transition TenderSubmission pk=%d to FLAGGED: %s",
            submission.pk,
            ve,
        )
        return

    # Write AuditLog entry for the red flag event
    try:
        from audit.models import AuditLog, EventType  # noqa: PLC0415

        AuditLog.objects.create(
            event_type=EventType.RED_FLAG_RAISED,
            user=None,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(submission.pk),
            data_snapshot={
                "red_flag_id": instance.pk,
                "flag_type": instance.flag_type,
                "severity": instance.severity,
                "tender_id": tender.pk,
                "submission_id": submission.pk,
                "agency_id": str(submission.agency.agency_id),
                "previous_status": SubmissionStatus.UNDER_REVIEW,
                "new_status": SubmissionStatus.FLAGGED,
            },
        )
    except Exception as exc:
        logger.error(
            "agencies: Failed to write AuditLog for RedFlag pk=%d: %s",
            instance.pk,
            exc,
        )

    # Enqueue the Agency_Admin email notification within 5 minutes (Requirement 7.4).
    # countdown=0 means it runs as soon as a worker picks it up; the 5-minute SLA
    # is satisfied as long as a Celery worker is available.
    try:
        from agencies.tasks import notify_agency_admin_flagged  # noqa: PLC0415

        notify_agency_admin_flagged.apply_async(
            args=[submission.pk],
            countdown=0,  # dispatch immediately; worker SLA ≤ 5 minutes
        )
        logger.info(
            "agencies: Enqueued notify_agency_admin_flagged for submission pk=%d.",
            submission.pk,
        )
    except Exception as exc:
        logger.error(
            "agencies: Failed to enqueue notify_agency_admin_flagged for "
            "submission pk=%d: %s",
            submission.pk,
            exc,
        )
