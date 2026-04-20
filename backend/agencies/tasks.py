"""
agencies/tasks.py

Celery tasks for the Agency Portal RBAC feature.

Tasks:
  - send_verification_email(user_id, token_hex, agency_name)
      Send email verification link to a newly registered agency admin.
      Retries up to 3 times with exponential backoff.
      On permanent failure: marks EmailVerificationToken.delivery_failed=True
      and creates an internal Alert for all ADMIN users.

  - send_invitation_email(invitation_id, token_hex)
      Send invitation email with the token link to the invitee's email.
      Retries up to 3 times with exponential backoff on failure.

Requirements: 1.8, 4.2
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 60  # seconds; actual delay = RETRY_BACKOFF_BASE * 2^(attempt-1)


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF_BASE,
)
def send_verification_email(self, user_id: int, token_hex: str, agency_name: str) -> None:
    """
    Send an email verification link to the agency admin.

    Args:
        user_id:     PK of the User record (Agency_Admin).
        token_hex:   Raw 32-byte token as a hex string (NOT the stored hash).
        agency_name: Human-readable agency name for the email body.

    On permanent failure (after MAX_RETRIES):
        - Sets EmailVerificationToken.delivery_failed = True
        - Creates an internal Alert for all ADMIN users
    """
    from authentication.models import User, UserRole  # noqa: PLC0415

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        logger.warning("send_verification_email: User pk=%d not found.", user_id)
        return

    # Build the verification URL
    frontend_origin = getattr(settings, "FRONTEND_ORIGIN", "http://localhost:3000")
    verification_url = f"{frontend_origin}/agency/verify-email?token={token_hex}"

    subject = "[TenderShield] Verify your agency email address"
    body = _build_verification_email_body(user.email, agency_name, verification_url)

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
        logger.info(
            "Verification email sent to %s for agency '%s'.", user.email, agency_name
        )

    except Exception as exc:
        logger.error(
            "Failed to send verification email to %s (attempt %d/%d): %s",
            user.email,
            self.request.retries + 1,
            MAX_RETRIES,
            exc,
        )

        if self.request.retries < MAX_RETRIES:
            # Exponential backoff: 60s, 120s, 240s
            countdown = RETRY_BACKOFF_BASE * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)

        # Permanent failure — all retries exhausted
        _handle_permanent_failure(user_id, agency_name, str(exc))


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_verification_email_body(email: str, agency_name: str, verification_url: str) -> str:
    return (
        f"Welcome to TenderShield!\n\n"
        f"You have registered '{agency_name}' on TenderShield — India's government "
        f"procurement fraud detection platform.\n\n"
        f"Please verify your email address by clicking the link below:\n\n"
        f"  {verification_url}\n\n"
        f"This link expires in 24 hours.\n\n"
        f"If you did not register on TenderShield, please ignore this email.\n\n"
        f"— The TenderShield Team\n"
    )


def _handle_permanent_failure(user_id: int, agency_name: str, error: str) -> None:
    """
    Called when all retries are exhausted.

    1. Marks EmailVerificationToken.delivery_failed = True.
    2. Creates an internal Alert for all ADMIN users.
    """
    from agencies.models import EmailVerificationToken  # noqa: PLC0415
    from authentication.models import User, UserRole  # noqa: PLC0415

    # Mark the token as delivery-failed
    try:
        token = EmailVerificationToken.objects.get(user_id=user_id)
        token.delivery_failed = True
        token.save(update_fields=["delivery_failed"])
        logger.warning(
            "Marked EmailVerificationToken delivery_failed=True for user_id=%d.", user_id
        )
    except EmailVerificationToken.DoesNotExist:
        logger.warning(
            "EmailVerificationToken not found for user_id=%d during failure handling.", user_id
        )

    # Create internal alerts for all ADMIN users
    _create_admin_alerts(user_id, agency_name, error)


def _create_admin_alerts(user_id: int, agency_name: str, error: str) -> None:
    """Create an internal Alert for every ADMIN user to flag the delivery failure."""
    from authentication.models import User, UserRole  # noqa: PLC0415

    admin_users = list(
        User.objects.filter(role=UserRole.ADMIN, is_active=True)
    )

    if not admin_users:
        logger.warning("No ADMIN users found to notify about verification email failure.")
        return

    # We create a lightweight notification via AuditLog since Alert requires a Tender FK.
    # A proper Alert model extension (without Tender FK) is out of scope for this task.
    from audit.models import AuditLog, EventType  # noqa: PLC0415

    for admin in admin_users:
        try:
            AuditLog.objects.create(
                event_type=EventType.ALERT_FAILED,
                user=admin,
                affected_entity_type="EmailVerificationToken",
                affected_entity_id=str(user_id),
                data_snapshot={
                    "user_id": user_id,
                    "agency_name": agency_name,
                    "error": error,
                    "message": (
                        f"Verification email delivery permanently failed for agency "
                        f"'{agency_name}' (user_id={user_id}). Manual intervention required."
                    ),
                },
            )
        except Exception as log_exc:
            logger.error(
                "Failed to write AuditLog for admin alert (user_id=%d): %s",
                admin.pk,
                log_exc,
            )

    logger.warning(
        "Created %d admin alert(s) for permanent verification email failure "
        "(user_id=%d, agency='%s').",
        len(admin_users),
        user_id,
        agency_name,
    )


# ---------------------------------------------------------------------------
# Task 4.4 — send_invitation_email
# Requirements: 4.2
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF_BASE,
)
def send_invitation_email(self, invitation_id: int, token_hex: str) -> None:
    """
    Send an invitation email to the invitee.

    Args:
        invitation_id: PK of the Invitation record.
        token_hex:     Raw 32-byte token as a hex string (NOT the stored hash).

    On permanent failure (after MAX_RETRIES):
        - Logs the error; the invitation remains in the DB for manual follow-up.
    """
    from agencies.models import Invitation  # noqa: PLC0415

    try:
        invitation = Invitation.objects.select_related("agency").get(pk=invitation_id)
    except Invitation.DoesNotExist:
        logger.warning("send_invitation_email: Invitation pk=%d not found.", invitation_id)
        return

    frontend_origin = getattr(settings, "FRONTEND_ORIGIN", "http://localhost:3000")
    invitation_url = f"{frontend_origin}/agency/invite/{token_hex}"

    subject = "[TenderShield] You have been invited to join an agency"
    body = _build_invitation_email_body(
        email=invitation.email,
        agency_name=invitation.agency.legal_name,
        role=invitation.role,
        invitation_url=invitation_url,
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
            fail_silently=False,
        )
        logger.info(
            "Invitation email sent to %s for agency '%s' (role=%s).",
            invitation.email,
            invitation.agency.legal_name,
            invitation.role,
        )

    except Exception as exc:
        logger.error(
            "Failed to send invitation email to %s (attempt %d/%d): %s",
            invitation.email,
            self.request.retries + 1,
            MAX_RETRIES,
            exc,
        )

        if self.request.retries < MAX_RETRIES:
            countdown = RETRY_BACKOFF_BASE * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)

        # Permanent failure — log and notify admins via AuditLog
        logger.error(
            "Permanent failure sending invitation email to %s for invitation_id=%d.",
            invitation.email,
            invitation_id,
        )
        _notify_admins_invitation_failure(invitation_id, invitation.email, str(exc))


def _build_invitation_email_body(
    email: str, agency_name: str, role: str, invitation_url: str
) -> str:
    role_display = role.replace("_", " ").title()
    return (
        f"Hello,\n\n"
        f"You have been invited to join '{agency_name}' on TenderShield as a "
        f"{role_display}.\n\n"
        f"Click the link below to accept the invitation and create your account:\n\n"
        f"  {invitation_url}\n\n"
        f"This invitation link expires in 72 hours.\n\n"
        f"If you did not expect this invitation, please ignore this email.\n\n"
        f"— The TenderShield Team\n"
    )


def _notify_admins_invitation_failure(
    invitation_id: int, invitee_email: str, error: str
) -> None:
    """Write an AuditLog entry for all ADMIN users when invitation email delivery fails."""
    from audit.models import AuditLog, EventType  # noqa: PLC0415
    from authentication.models import User, UserRole  # noqa: PLC0415

    admin_users = list(User.objects.filter(role=UserRole.ADMIN, is_active=True))
    for admin in admin_users:
        try:
            AuditLog.objects.create(
                event_type=EventType.ALERT_FAILED,
                user=admin,
                affected_entity_type="Invitation",
                affected_entity_id=str(invitation_id),
                data_snapshot={
                    "invitation_id": invitation_id,
                    "invitee_email": invitee_email,
                    "error": error,
                    "message": (
                        f"Invitation email delivery permanently failed for "
                        f"{invitee_email} (invitation_id={invitation_id}). "
                        f"Manual intervention required."
                    ),
                },
            )
        except Exception as log_exc:
            logger.error(
                "Failed to write AuditLog for invitation failure (invitation_id=%d): %s",
                invitation_id,
                log_exc,
            )


# ---------------------------------------------------------------------------
# Task 6.6 / 7.1 — score_agency_tender
# Enqueued when a TenderSubmission is promoted to SUBMITTED status.
# Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF_BASE,
)
def score_agency_tender(self, submission_id: int) -> None:
    """
    Run the fraud detection pipeline on the Tender linked to a TenderSubmission.

    Steps:
    1. Load the TenderSubmission and its linked Tender.
    2. Call the existing score_tender pipeline (ml_worker) on the Tender, then
       run RiskScorer.compute_score() to aggregate rule-based flags + ML scores.
    3. Update TenderSubmission status based on the resulting fraud risk score:
       - score >= 70  -> UNDER_REVIEW (via transition_to)
       - score < 40   -> CLEARED (via transition_to)
       - 40 <= score < 70 -> leave as SUBMITTED (manual review)
    4. If score >= 70, create Alert records for all AGENCY_ADMIN and
       AGENCY_OFFICER users of the submitting agency.
    5. Write AuditLog entry.

    On permanent failure (after MAX_RETRIES):
    - TenderSubmission.status remains SUBMITTED.
    - Creates internal Alert for all ADMIN users with alert_type=SCORING_FAILURE.
    - Writes AuditLog entry with error details.

    Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7
    """
    from agencies.models import SubmissionStatus, TenderSubmission  # noqa: PLC0415
    from audit.models import AuditLog, EventType  # noqa: PLC0415

    try:
        submission = TenderSubmission.objects.select_related(
            "agency", "tender", "submitted_by"
        ).get(pk=submission_id)
    except TenderSubmission.DoesNotExist:
        logger.warning("score_agency_tender: TenderSubmission pk=%d not found.", submission_id)
        return

    if submission.tender is None:
        logger.warning(
            "score_agency_tender: TenderSubmission pk=%d has no linked Tender.", submission_id
        )
        return

    tender = submission.tender

    try:
        # Step 1: Run the ML scoring pipeline (ml_worker.score_tender).
        # This writes/updates FraudRiskScore with ML scores.
        from ml_worker.tasks import score_tender  # noqa: PLC0415
        score_tender(tender.pk)

        # Step 2: Run the rule-based aggregation via RiskScorer.compute_score().
        # This reads active RedFlags + ML scores and writes the final integer score.
        from scoring.scorer import RiskScorer  # noqa: PLC0415
        scorer = RiskScorer()
        score_record = scorer.compute_score(tender.pk)
        score_value = float(score_record.score)

        # Step 3: Update TenderSubmission status based on score (Requirement 10.6)
        if score_value >= 70:
            try:
                submission.transition_to(SubmissionStatus.UNDER_REVIEW, actor=None)
            except ValueError as ve:
                logger.warning(
                    "score_agency_tender: Could not transition submission pk=%d to "
                    "UNDER_REVIEW: %s",
                    submission_id,
                    ve,
                )
        elif score_value < 40:
            try:
                submission.transition_to(SubmissionStatus.CLEARED, actor=None)
            except ValueError as ve:
                logger.warning(
                    "score_agency_tender: Could not transition submission pk=%d to "
                    "CLEARED: %s",
                    submission_id,
                    ve,
                )

        # Step 4: Write SCORE_COMPUTED AuditLog entry (Requirement 10.3)
        AuditLog.objects.create(
            event_type=EventType.SCORE_COMPUTED,
            user=None,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(submission_id),
            data_snapshot={
                "tender_id": tender.pk,
                "fraud_risk_score": score_value,
                "agency_id": str(submission.agency.agency_id),
                "new_status": submission.status,
            },
        )

        # Step 5: If score >= 70, create Alert records for agency admin/officer users
        # (Requirements 10.4, 10.5)
        if score_value >= 70:
            _alert_agency_users_high_risk(submission, score_value)

        logger.info(
            "score_agency_tender: Scored submission pk=%d — score=%.1f, new_status=%s.",
            submission_id,
            score_value,
            submission.status,
        )

    except Exception as exc:
        logger.error(
            "score_agency_tender: Error scoring submission pk=%d (attempt %d/%d): %s",
            submission_id,
            self.request.retries + 1,
            MAX_RETRIES,
            exc,
        )

        if self.request.retries < MAX_RETRIES:
            # Exponential backoff: 60s, 120s, 240s
            countdown = RETRY_BACKOFF_BASE * (2 ** self.request.retries)
            raise self.retry(exc=exc, countdown=countdown)

        # Permanent failure — all retries exhausted (Requirement 10.7)
        _handle_scoring_permanent_failure(submission_id, str(exc))


def _alert_agency_users_high_risk(submission, score_value: float) -> None:
    """
    Create Alert records for all AGENCY_ADMIN and AGENCY_OFFICER users
    of the submitting agency when fraud risk score >= 70.
    Also enqueues send_alert_email tasks for each created alert.
    Requirements: 10.4, 10.5
    """
    from alerts.models import Alert, AlertType, DeliveryStatus  # noqa: PLC0415
    from alerts.tasks import send_alert_email  # noqa: PLC0415
    from audit.models import AuditLog, EventType  # noqa: PLC0415
    from authentication.models import User, UserRole  # noqa: PLC0415

    tender = submission.tender
    agency_users = list(
        User.objects.filter(
            agency=submission.agency,
            role__in=[UserRole.AGENCY_ADMIN, UserRole.AGENCY_OFFICER],
            is_active=True,
        )
    )

    if not agency_users:
        logger.info(
            "score_agency_tender: No AGENCY_ADMIN/AGENCY_OFFICER users found for "
            "agency pk=%d.",
            submission.agency.pk,
        )
        return

    frontend_origin = getattr(settings, "FRONTEND_ORIGIN", "http://localhost:3000")
    detail_link = f"{frontend_origin}/agency/tenders/{submission.pk}"

    # Build top red flags for the alert payload
    top_red_flags = _get_top_red_flags(tender.pk)

    created_alerts = []
    for user in agency_users:
        try:
            alert = Alert.objects.create(
                tender=tender,
                user=user,
                alert_type=AlertType.HIGH_RISK_SCORE,
                title=(
                    f"High Fraud Risk: {submission.tender_ref} — "
                    f"Score {int(score_value)}"
                ),
                detail_link=detail_link,
                fraud_risk_score=int(score_value),
                top_red_flags=top_red_flags,
                delivery_status=DeliveryStatus.PENDING,
            )
            created_alerts.append(alert)
        except Exception as exc:
            logger.error(
                "Failed to create high-risk Alert for user pk=%d: %s", user.pk, exc
            )

    # Write a single AuditLog entry for the batch of alerts
    if created_alerts:
        try:
            AuditLog.objects.create(
                event_type=EventType.ALERT_SENT,
                user=None,
                affected_entity_type="TenderSubmission",
                affected_entity_id=str(submission.pk),
                data_snapshot={
                    "fraud_risk_score": score_value,
                    "tender_ref": submission.tender_ref,
                    "agency_id": str(submission.agency.agency_id),
                    "alert_ids": [a.pk for a in created_alerts],
                    "recipient_count": len(created_alerts),
                    "message": (
                        f"High fraud risk score ({score_value:.1f}) detected for "
                        f"tender '{submission.tender_ref}'. Tender is now UNDER_REVIEW."
                    ),
                },
            )
        except Exception as exc:
            logger.error(
                "Failed to write AuditLog for high-risk alerts (submission_id=%d): %s",
                submission.pk,
                exc,
            )

        # Enqueue email tasks for each alert
        for alert in created_alerts:
            try:
                send_alert_email.delay(alert.pk)
            except Exception as exc:
                logger.warning(
                    "Failed to enqueue send_alert_email for alert pk=%d: %s", alert.pk, exc
                )

    logger.info(
        "score_agency_tender: Created %d high-risk alert(s) for submission pk=%d "
        "(score=%.1f).",
        len(created_alerts),
        submission.pk,
        score_value,
    )


def _get_top_red_flags(tender_id: int) -> list:
    """Return the top 3 active red flags for the tender as a list of dicts."""
    from detection.models import RedFlag, Severity  # noqa: PLC0415

    severity_order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    flags = list(
        RedFlag.objects.filter(tender_id=tender_id, is_active=True)
        .values("flag_type", "severity", "trigger_data")[:10]
    )
    flags.sort(key=lambda f: severity_order.get(f["severity"], 99))
    return flags[:3]


def _handle_scoring_permanent_failure(submission_id: int, error: str) -> None:
    """
    Called when all score_agency_tender retries are exhausted.

    - TenderSubmission.status remains SUBMITTED (no transition).
    - Creates an internal Alert for all ADMIN users with alert_type=SCORING_FAILURE.
    - Writes AuditLog entry with error details.

    Requirements: 10.7
    """
    from alerts.models import Alert, AlertType, DeliveryStatus  # noqa: PLC0415
    from alerts.tasks import send_alert_email  # noqa: PLC0415
    from audit.models import AuditLog, EventType  # noqa: PLC0415
    from authentication.models import User, UserRole  # noqa: PLC0415

    admin_users = list(User.objects.filter(role=UserRole.ADMIN, is_active=True))

    if not admin_users:
        logger.warning(
            "score_agency_tender: No ADMIN users found to notify about scoring failure "
            "(submission_id=%d).",
            submission_id,
        )
    else:
        # Try to get the linked Tender for the Alert FK (required field)
        tender = None
        try:
            from agencies.models import TenderSubmission  # noqa: PLC0415
            submission = TenderSubmission.objects.select_related("tender").get(pk=submission_id)
            tender = submission.tender
        except Exception:
            pass

        created_alerts = []
        for admin in admin_users:
            try:
                if tender is not None:
                    alert = Alert.objects.create(
                        tender=tender,
                        user=admin,
                        alert_type=AlertType.SCORING_FAILURE,
                        title=(
                            f"Scoring Failure: TenderSubmission pk={submission_id}"
                        ),
                        detail_link="",
                        fraud_risk_score=0,
                        top_red_flags=[],
                        delivery_status=DeliveryStatus.PENDING,
                    )
                    created_alerts.append(alert)
                else:
                    # Tender not available — fall back to AuditLog-only notification
                    AuditLog.objects.create(
                        event_type=EventType.ALERT_FAILED,
                        user=admin,
                        affected_entity_type="TenderSubmission",
                        affected_entity_id=str(submission_id),
                        data_snapshot={
                            "submission_id": submission_id,
                            "error": error,
                            "message": (
                                f"Fraud scoring permanently failed for TenderSubmission "
                                f"pk={submission_id} after {MAX_RETRIES} retries. "
                                f"No linked Tender found. Manual intervention required."
                            ),
                        },
                    )
            except Exception as log_exc:
                logger.error(
                    "Failed to create scoring-failure Alert for admin pk=%d: %s",
                    admin.pk,
                    log_exc,
                )

        # Enqueue email tasks for created alerts
        for alert in created_alerts:
            try:
                send_alert_email.delay(alert.pk)
            except Exception as exc:
                logger.warning(
                    "Failed to enqueue send_alert_email for scoring-failure alert pk=%d: %s",
                    alert.pk,
                    exc,
                )

    # Write AuditLog entry with error details (always, regardless of Alert creation)
    try:
        AuditLog.objects.create(
            event_type=EventType.ALERT_FAILED,
            user=None,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(submission_id),
            data_snapshot={
                "submission_id": submission_id,
                "error": error,
                "retries_exhausted": MAX_RETRIES,
                "message": (
                    f"Fraud scoring permanently failed for TenderSubmission "
                    f"pk={submission_id} after {MAX_RETRIES} retries. "
                    f"Manual intervention required."
                ),
            },
        )
    except Exception as log_exc:
        logger.error(
            "Failed to write AuditLog for scoring permanent failure "
            "(submission_id=%d): %s",
            submission_id,
            log_exc,
        )

    logger.error(
        "Permanent scoring failure for TenderSubmission pk=%d. "
        "Notified %d admin(s). Error: %s",
        submission_id,
        len(admin_users),
        error,
    )


# ---------------------------------------------------------------------------
# Task 7.3 — notify_agency_admin_flagged
# Dispatches email to Agency_Admin when a TenderSubmission is FLAGGED.
# Triggered by the RedFlag post_save signal (see agencies/apps.py).
# Requirements: 7.4
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    max_retries=MAX_RETRIES,
    default_retry_delay=RETRY_BACKOFF_BASE,
)
def notify_agency_admin_flagged(self, submission_id: int) -> None:
    """
    Send an email notification to all Agency_Admin users of the submitting
    agency when a TenderSubmission transitions to FLAGGED status.

    This task is enqueued by the RedFlag post_save signal handler in
    agencies/apps.py with a countdown of up to 5 minutes (Requirement 7.4).

    Steps:
    1. Load the TenderSubmission and its agency.
    2. Find all AGENCY_ADMIN users for the agency.
    3. Send an email to each Agency_Admin.
    4. Write AuditLog entry.

    Requirements: 7.4
    """
    from agencies.models import TenderSubmission  # noqa: PLC0415
    from audit.models import AuditLog, EventType  # noqa: PLC0415
    from authentication.models import User, UserRole  # noqa: PLC0415

    try:
        submission = TenderSubmission.objects.select_related(
            "agency", "tender"
        ).get(pk=submission_id)
    except TenderSubmission.DoesNotExist:
        logger.warning(
            "notify_agency_admin_flagged: TenderSubmission pk=%d not found.",
            submission_id,
        )
        return

    agency = submission.agency
    admin_users = list(
        User.objects.filter(
            agency=agency,
            role=UserRole.AGENCY_ADMIN,
            is_active=True,
        )
    )

    if not admin_users:
        logger.warning(
            "notify_agency_admin_flagged: No AGENCY_ADMIN users found for "
            "agency pk=%d (submission_id=%d).",
            agency.pk,
            submission_id,
        )
        return

    subject = (
        f"[TenderShield] Tender Flagged for Review — {submission.tender_ref}"
    )
    body = _build_flagged_email_body(submission, agency)

    sent_to = []
    failed = []
    for admin in admin_users:
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[admin.email],
                fail_silently=False,
            )
            sent_to.append(admin.email)
            logger.info(
                "notify_agency_admin_flagged: Email sent to %s for submission pk=%d.",
                admin.email,
                submission_id,
            )
        except Exception as exc:
            failed.append(admin.email)
            logger.error(
                "notify_agency_admin_flagged: Failed to send email to %s "
                "(submission_id=%d, attempt %d/%d): %s",
                admin.email,
                submission_id,
                self.request.retries + 1,
                MAX_RETRIES,
                exc,
            )

    # Retry if any sends failed and retries remain
    if failed and self.request.retries < MAX_RETRIES:
        countdown = RETRY_BACKOFF_BASE * (2 ** self.request.retries)
        raise self.retry(
            exc=Exception(f"Email delivery failed for: {failed}"),
            countdown=countdown,
        )

    # Write AuditLog entry (Requirement 7.3 / 7.4)
    try:
        AuditLog.objects.create(
            event_type=EventType.ALERT_SENT,
            user=None,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(submission_id),
            data_snapshot={
                "submission_id": submission_id,
                "tender_ref": submission.tender_ref,
                "agency_id": str(agency.agency_id),
                "sent_to": sent_to,
                "failed": failed,
                "message": (
                    f"Tender '{submission.tender_ref}' has been FLAGGED. "
                    f"Agency_Admin notification email dispatched."
                ),
            },
        )
    except Exception as log_exc:
        logger.error(
            "notify_agency_admin_flagged: Failed to write AuditLog "
            "(submission_id=%d): %s",
            submission_id,
            log_exc,
        )


def _build_flagged_email_body(submission, agency) -> str:
    """Build the plain-text email body for a FLAGGED tender notification."""
    frontend_origin = getattr(settings, "FRONTEND_ORIGIN", "http://localhost:3000")
    detail_link = f"{frontend_origin}/agency/tenders/{submission.pk}"
    return (
        f"TenderShield — Tender Flagged for Review\n"
        f"{'=' * 45}\n\n"
        f"Agency: {agency.legal_name}\n"
        f"Tender Reference: {submission.tender_ref}\n"
        f"Title: {submission.title}\n"
        f"Status: FLAGGED\n\n"
        f"One or more fraud indicators have been detected for this tender. "
        f"It has been flagged for manual review by a Government Auditor or "
        f"TenderShield Administrator.\n\n"
        f"Please review the tender details and any associated red flags:\n\n"
        f"  {detail_link}\n\n"
        f"No action is required from your side at this time. You will be "
        f"notified once the review is complete.\n\n"
        f"DISCLAIMER: This flag is advisory only. Human review is required "
        f"before initiating any legal or administrative action.\n\n"
        f"— The TenderShield Team\n"
    )
