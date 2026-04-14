"""
Celery tasks for the Alert System.

Tasks:
  - send_alert_email(alert_id): Send email notification for a single alert.
  - retry_failed_emails(): Beat task — retry FAILED alerts up to 3 times.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_RETRY_COUNT = 3


@shared_task(bind=True, max_retries=0)
def send_alert_email(self, alert_id: int) -> None:
    """
    Send an email notification for the given Alert.

    If AlertSettings.email_enabled is False for the recipient, skip silently.
    On failure, set delivery_status = FAILED and log to AuditLog.
    """
    from alerts.models import Alert, AlertSettings, DeliveryStatus
    from audit.models import AuditLog, EventType

    try:
        alert = Alert.objects.select_related("user", "tender").get(pk=alert_id)
    except Alert.DoesNotExist:
        logger.warning("send_alert_email: Alert pk=%d not found.", alert_id)
        return

    # Check if email is enabled for this user
    email_enabled = _is_email_enabled(alert.user, alert.tender.category)
    if not email_enabled:
        logger.debug("Email disabled for user %d, skipping.", alert.user_id)
        return

    subject = f"[TenderShield] High Fraud Risk Alert — {alert.title or alert.tender.title}"
    body = _build_email_body(alert)
    recipient = alert.user.email

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        alert.delivery_status = DeliveryStatus.DELIVERED
        alert.delivered_at = timezone.now()
        alert.save(update_fields=["delivery_status", "delivered_at"])
        logger.info("Alert email sent for alert_id=%d to %s.", alert_id, recipient)

    except Exception as exc:
        logger.error("Failed to send alert email for alert_id=%d: %s", alert_id, exc)
        alert.delivery_status = DeliveryStatus.FAILED
        alert.save(update_fields=["delivery_status"])

        AuditLog.objects.create(
            event_type=EventType.ALERT_FAILED,
            user=alert.user,
            affected_entity_type="Alert",
            affected_entity_id=str(alert_id),
            data_snapshot={
                "alert_id": alert_id,
                "tender_id": alert.tender_id,
                "error": str(exc),
                "retry_count": alert.retry_count,
            },
        )


@shared_task
def retry_failed_emails() -> None:
    """
    Celery beat task: retry alerts with delivery_status=FAILED and retry_count < MAX_RETRY_COUNT.

    - Increments retry_count on each attempt.
    - After MAX_RETRY_COUNT failures, sets delivery_status = PERMANENTLY_FAILED.
    - Logs each failed attempt to AuditLog.
    """
    from alerts.models import Alert, AlertSettings, DeliveryStatus
    from audit.models import AuditLog, EventType

    failed_alerts = list(
        Alert.objects.select_related("user", "tender").filter(
            delivery_status=DeliveryStatus.FAILED,
            retry_count__lt=MAX_RETRY_COUNT,
        )
    )

    logger.info("retry_failed_emails: found %d failed alert(s) to retry.", len(failed_alerts))

    for alert in failed_alerts:
        email_enabled = _is_email_enabled(alert.user, alert.tender.category)
        if not email_enabled:
            continue

        subject = f"[TenderShield] High Fraud Risk Alert — {alert.title or alert.tender.title}"
        body = _build_email_body(alert)
        recipient = alert.user.email

        alert.retry_count += 1

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient],
                fail_silently=False,
            )
            alert.delivery_status = DeliveryStatus.DELIVERED
            alert.delivered_at = timezone.now()
            alert.save(update_fields=["delivery_status", "delivered_at", "retry_count"])
            logger.info("Retry succeeded for alert_id=%d.", alert.id)

        except Exception as exc:
            logger.error("Retry %d failed for alert_id=%d: %s", alert.retry_count, alert.id, exc)

            if alert.retry_count >= MAX_RETRY_COUNT:
                alert.delivery_status = DeliveryStatus.PERMANENTLY_FAILED
            # else keep as FAILED so it will be retried again

            alert.save(update_fields=["delivery_status", "retry_count"])

            AuditLog.objects.create(
                event_type=EventType.ALERT_FAILED,
                user=alert.user,
                affected_entity_type="Alert",
                affected_entity_id=str(alert.id),
                data_snapshot={
                    "alert_id": alert.id,
                    "tender_id": alert.tender_id,
                    "error": str(exc),
                    "retry_count": alert.retry_count,
                    "permanently_failed": alert.delivery_status == DeliveryStatus.PERMANENTLY_FAILED,
                },
            )


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _is_email_enabled(user, category: str) -> bool:
    """
    Return True if email notifications are enabled for this user.
    Checks per-category setting first, then global setting.
    Defaults to True if no AlertSettings exist.
    """
    from alerts.models import AlertSettings

    # Per-category
    if category:
        cat_setting = (
            AlertSettings.objects.filter(user=user, category=category)
            .order_by("-id")
            .first()
        )
        if cat_setting is not None:
            return cat_setting.email_enabled

    # Global
    global_setting = (
        AlertSettings.objects.filter(user=user, category="")
        .order_by("-id")
        .first()
    )
    if global_setting is not None:
        return global_setting.email_enabled

    return True  # default: email enabled


def _build_email_body(alert) -> str:
    """Build a plain-text email body for an alert."""
    flags_text = ""
    for i, flag in enumerate(alert.top_red_flags or [], start=1):
        flags_text += f"  {i}. {flag.get('flag_type', 'N/A')} ({flag.get('severity', 'N/A')})\n"

    none_text = "  None\n"
    return (
        f"TenderShield Fraud Risk Alert\n"
        f"{'=' * 40}\n\n"
        f"Tender: {alert.title or alert.tender.title}\n"
        f"Tender ID: {alert.tender.tender_id}\n"
        f"Fraud Risk Score: {alert.fraud_risk_score}\n\n"
        f"Top Red Flags:\n{flags_text or none_text}\n"
        f"View Details: {alert.detail_link}\n\n"
        f"DISCLAIMER: This score is advisory only. Human review is required "
        f"before initiating any legal or administrative action.\n"
    )
