"""
AlertSystem — evaluates fraud risk score thresholds and dispatches alerts.

Responsibilities:
  - Compare the latest FraudRiskScore against global and per-category thresholds.
  - Create Alert records for all AUDITOR and ADMIN users when threshold is crossed.
  - Write AuditLog entries when alerts are created.
"""

from __future__ import annotations

import logging
from typing import List

from django.utils import timezone

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 70


class AlertSystem:
    """Evaluates thresholds and creates Alert records."""

    def check_and_alert(self, tender_id: int) -> List:
        """
        Evaluate threshold rules for the given tender and create Alert records
        for all AUDITOR/ADMIN users if the latest score meets or exceeds the threshold.

        Returns the list of created Alert instances.
        """
        from alerts.models import Alert, AlertSettings, AlertType, DeliveryStatus
        from audit.models import AuditLog, EventType
        from authentication.models import User, UserRole
        from detection.models import RedFlag
        from scoring.models import FraudRiskScore
        from tenders.models import Tender

        # 1. Get the latest score for this tender
        latest_score = (
            FraudRiskScore.objects.filter(tender_id=tender_id)
            .order_by("-computed_at")
            .first()
        )
        if latest_score is None:
            logger.info("No FraudRiskScore found for tender_id=%d, skipping alert check.", tender_id)
            return []

        score_value = latest_score.score

        # 2. Get the tender to determine category and title
        try:
            tender = Tender.objects.get(pk=tender_id)
        except Tender.DoesNotExist:
            logger.warning("Tender pk=%d not found, skipping alert check.", tender_id)
            return []

        # 3. Determine the effective threshold for this tender's category
        threshold = self._resolve_threshold(tender.category)

        if score_value < threshold:
            logger.debug(
                "Score %d for tender_id=%d is below threshold %d, no alert.",
                score_value, tender_id, threshold,
            )
            return []

        # 4. Build top-3 red flags payload
        top_red_flags = self._get_top_red_flags(tender_id)

        # 5. Build detail link
        detail_link = f"/tenders/{tender_id}"

        # 6. Get all AUDITOR and ADMIN users
        recipients = list(
            User.objects.filter(
                role__in=[UserRole.AUDITOR, UserRole.ADMIN],
                is_active=True,
            )
        )

        if not recipients:
            logger.info("No AUDITOR/ADMIN users found, no alerts created.")
            return []

        # 7. Create Alert records
        created_alerts = []
        for user in recipients:
            alert = Alert.objects.create(
                tender=tender,
                user=user,
                alert_type=AlertType.HIGH_RISK_SCORE,
                title=tender.title,
                detail_link=detail_link,
                fraud_risk_score=score_value,
                top_red_flags=top_red_flags,
                delivery_status=DeliveryStatus.PENDING,
            )
            created_alerts.append(alert)

        # 8. Write AuditLog entry
        AuditLog.objects.create(
            event_type=EventType.ALERT_SENT,
            affected_entity_type="Tender",
            affected_entity_id=str(tender_id),
            data_snapshot={
                "tender_id": tender_id,
                "score": score_value,
                "threshold": threshold,
                "alert_count": len(created_alerts),
                "alert_ids": [a.id for a in created_alerts],
            },
        )

        logger.info(
            "Created %d alert(s) for tender_id=%d (score=%d, threshold=%d).",
            len(created_alerts), tender_id, score_value, threshold,
        )

        # 9. Enqueue email tasks for each alert
        self._enqueue_email_tasks(created_alerts)

        return created_alerts

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _resolve_threshold(self, category: str) -> int:
        """
        Return the effective threshold for the given category.
        Per-category AlertSettings (category != '') take precedence over global (category == '').
        Falls back to DEFAULT_THRESHOLD if no settings exist.
        """
        from alerts.models import AlertSettings

        # Try per-category override first
        if category:
            cat_setting = (
                AlertSettings.objects.filter(category=category)
                .order_by("-id")
                .first()
            )
            if cat_setting is not None:
                return cat_setting.threshold

        # Fall back to global setting
        global_setting = (
            AlertSettings.objects.filter(category="")
            .order_by("-id")
            .first()
        )
        if global_setting is not None:
            return global_setting.threshold

        return DEFAULT_THRESHOLD

    def _get_top_red_flags(self, tender_id: int) -> list:
        """Return the top 3 active red flags for the tender as a list of dicts."""
        from detection.models import RedFlag, Severity

        severity_order = {
            Severity.HIGH: 0,
            Severity.MEDIUM: 1,
            Severity.LOW: 2,
        }

        flags = list(
            RedFlag.objects.filter(tender_id=tender_id, is_active=True)
            .order_by("severity")
            .values("flag_type", "severity", "trigger_data")[:10]
        )

        # Sort by severity priority then take top 3
        flags.sort(key=lambda f: severity_order.get(f["severity"], 99))
        return flags[:3]

    def _enqueue_email_tasks(self, alerts: list) -> None:
        """Enqueue send_alert_email Celery tasks for each alert."""
        try:
            from alerts.tasks import send_alert_email
            for alert in alerts:
                send_alert_email.delay(alert.id)
        except Exception as exc:
            logger.warning("Failed to enqueue email tasks: %s", exc)
