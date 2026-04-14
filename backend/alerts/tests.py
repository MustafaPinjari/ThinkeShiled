"""
Unit tests for the AlertSystem (Task 16).

Covers:
  - Threshold firing: alert created when score >= threshold, not when score < threshold
  - Per-category threshold override: category-specific threshold takes precedence
  - Alert content: tender_id, title, score, top 3 red flags, detail link
  - Retry logic: retry_failed_emails retries up to 3 times, stops after 3 failures
  - 90-day history filter: alerts older than 90 days excluded from list endpoint
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from alerts.alert_system import AlertSystem, DEFAULT_THRESHOLD
from alerts.models import Alert, AlertSettings, DeliveryStatus
from alerts.tasks import retry_failed_emails, MAX_RETRY_COUNT
from audit.models import AuditLog
from authentication.models import User, UserRole
from detection.models import RedFlag, Severity, FlagType
from scoring.models import FraudRiskScore
from tenders.models import Tender


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_user(username, role=UserRole.AUDITOR, email=None):
    return User.objects.create_user(
        username=username,
        email=email or f"{username}@example.com",
        password="testpass123",
        role=role,
    )


def make_tender(tender_id="T001", category="IT", title="Test Tender"):
    return Tender.objects.create(
        tender_id=tender_id,
        title=title,
        category=category,
        estimated_value="100000.00",
        currency="INR",
        submission_deadline=timezone.now() + timedelta(days=30),
        buyer_id="B001",
        buyer_name="Test Buyer",
    )


def make_score(tender, score):
    return FraudRiskScore.objects.create(
        tender=tender,
        score=score,
        computed_at=timezone.now(),
    )


def make_red_flag(tender, flag_type=FlagType.SINGLE_BIDDER, severity=Severity.HIGH):
    return RedFlag.objects.create(
        tender=tender,
        flag_type=flag_type,
        severity=severity,
        trigger_data={"test": True},
        is_active=True,
    )


def get_jwt(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token)


# ---------------------------------------------------------------------------
# 16.1 — AlertSystem.check_and_alert
# ---------------------------------------------------------------------------

class AlertSystemThresholdTest(TestCase):
    """Threshold firing: alert created when score >= threshold, not when score < threshold."""

    def setUp(self):
        self.auditor = make_user("auditor1", UserRole.AUDITOR)
        self.admin = make_user("admin1", UserRole.ADMIN)
        self.tender = make_tender()

    def test_alert_created_when_score_meets_threshold(self):
        """Score == default threshold (70) should create alerts."""
        make_score(self.tender, DEFAULT_THRESHOLD)
        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertEqual(len(alerts), 2)  # auditor + admin

    def test_alert_created_when_score_exceeds_threshold(self):
        """Score > threshold should create alerts."""
        make_score(self.tender, 85)
        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertGreater(len(alerts), 0)

    def test_no_alert_when_score_below_threshold(self):
        """Score < threshold should NOT create alerts."""
        make_score(self.tender, DEFAULT_THRESHOLD - 1)
        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertEqual(len(alerts), 0)

    def test_no_alert_when_no_score_exists(self):
        """No FraudRiskScore → no alerts."""
        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertEqual(len(alerts), 0)

    def test_alerts_created_for_auditor_and_admin_only(self):
        """Alerts are created for AUDITOR and ADMIN users only."""
        make_score(self.tender, 80)
        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        user_ids = {a.user_id for a in alerts}
        self.assertIn(self.auditor.pk, user_ids)
        self.assertIn(self.admin.pk, user_ids)

    def test_audit_log_written_when_alerts_created(self):
        """AuditLog entry is written when alerts are created."""
        make_score(self.tender, 80)
        system = AlertSystem()
        system.check_and_alert(self.tender.pk)
        self.assertTrue(
            AuditLog.objects.filter(
                event_type="ALERT_SENT",
                affected_entity_id=str(self.tender.pk),
            ).exists()
        )


class AlertSystemPerCategoryThresholdTest(TestCase):
    """Per-category threshold override takes precedence over global."""

    def setUp(self):
        self.auditor = make_user("auditor2", UserRole.AUDITOR)
        self.tender = make_tender(category="Construction")

    def test_category_threshold_overrides_global(self):
        """Category threshold 90 should suppress alert for score 80."""
        # Global threshold = 70, category threshold = 90
        AlertSettings.objects.create(user=self.auditor, category="", threshold=70)
        AlertSettings.objects.create(user=self.auditor, category="Construction", threshold=90)
        make_score(self.tender, 80)

        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertEqual(len(alerts), 0)

    def test_category_threshold_fires_when_score_meets_it(self):
        """Category threshold 60 should fire for score 65."""
        AlertSettings.objects.create(user=self.auditor, category="", threshold=70)
        AlertSettings.objects.create(user=self.auditor, category="Construction", threshold=60)
        make_score(self.tender, 65)

        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertGreater(len(alerts), 0)

    def test_global_threshold_used_when_no_category_override(self):
        """Global threshold used when no per-category setting exists."""
        AlertSettings.objects.create(user=self.auditor, category="", threshold=80)
        make_score(self.tender, 75)

        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertEqual(len(alerts), 0)


class AlertContentTest(TestCase):
    """Alert content: verify tender_id, title, score, top 3 red flags, detail link."""

    def setUp(self):
        self.auditor = make_user("auditor3", UserRole.AUDITOR)
        self.tender = make_tender(tender_id="T999", title="My Tender")

    def test_alert_content_fields(self):
        """Alert must contain tender_id, title, score, top 3 red flags, detail link."""
        make_score(self.tender, 80)
        make_red_flag(self.tender, FlagType.SINGLE_BIDDER, Severity.HIGH)
        make_red_flag(self.tender, FlagType.PRICE_ANOMALY, Severity.MEDIUM)
        make_red_flag(self.tender, FlagType.REPEAT_WINNER, Severity.HIGH)
        make_red_flag(self.tender, FlagType.SHORT_DEADLINE, Severity.MEDIUM)  # 4th flag

        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertGreater(len(alerts), 0)

        alert = alerts[0]
        self.assertEqual(alert.tender_id, self.tender.pk)
        self.assertEqual(alert.title, "My Tender")
        self.assertEqual(alert.fraud_risk_score, 80)
        self.assertEqual(alert.detail_link, f"/tenders/{self.tender.pk}")
        # Top 3 red flags only
        self.assertEqual(len(alert.top_red_flags), 3)

    def test_alert_top_red_flags_limited_to_3(self):
        """Even with 5 red flags, only top 3 are stored."""
        make_score(self.tender, 90)
        for _ in range(5):
            make_red_flag(self.tender, FlagType.SINGLE_BIDDER, Severity.HIGH)

        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertEqual(len(alerts[0].top_red_flags), 3)

    def test_alert_with_no_red_flags(self):
        """Alert can be created even with no red flags."""
        make_score(self.tender, 75)
        system = AlertSystem()
        alerts = system.check_and_alert(self.tender.pk)
        self.assertGreater(len(alerts), 0)
        self.assertEqual(alerts[0].top_red_flags, [])


# ---------------------------------------------------------------------------
# 16.3 — send_alert_email Celery task
# ---------------------------------------------------------------------------

class SendAlertEmailTaskTest(TestCase):
    """Email task sends email when email_enabled=True, skips when False."""

    def setUp(self):
        self.auditor = make_user("auditor4", UserRole.AUDITOR)
        self.tender = make_tender()

    def _make_alert(self):
        return Alert.objects.create(
            tender=self.tender,
            user=self.auditor,
            title=self.tender.title,
            detail_link=f"/tenders/{self.tender.pk}",
            fraud_risk_score=80,
            top_red_flags=[],
            delivery_status=DeliveryStatus.PENDING,
        )

    @patch("alerts.tasks.send_mail")
    def test_email_sent_when_enabled(self, mock_send_mail):
        """Email is sent when email_enabled=True."""
        AlertSettings.objects.create(user=self.auditor, category="", email_enabled=True, threshold=70)
        alert = self._make_alert()

        from alerts.tasks import send_alert_email
        send_alert_email(alert.pk)

        mock_send_mail.assert_called_once()
        alert.refresh_from_db()
        self.assertEqual(alert.delivery_status, DeliveryStatus.DELIVERED)

    @patch("alerts.tasks.send_mail")
    def test_email_skipped_when_disabled(self, mock_send_mail):
        """Email is NOT sent when email_enabled=False."""
        AlertSettings.objects.create(user=self.auditor, category="", email_enabled=False, threshold=70)
        alert = self._make_alert()

        from alerts.tasks import send_alert_email
        send_alert_email(alert.pk)

        mock_send_mail.assert_not_called()

    @patch("alerts.tasks.send_mail", side_effect=Exception("SMTP error"))
    def test_email_failure_sets_failed_status(self, mock_send_mail):
        """On send failure, delivery_status is set to FAILED and AuditLog written."""
        AlertSettings.objects.create(user=self.auditor, category="", email_enabled=True, threshold=70)
        alert = self._make_alert()

        from alerts.tasks import send_alert_email
        send_alert_email(alert.pk)

        alert.refresh_from_db()
        self.assertEqual(alert.delivery_status, DeliveryStatus.FAILED)
        self.assertTrue(
            AuditLog.objects.filter(event_type="ALERT_FAILED", affected_entity_id=str(alert.pk)).exists()
        )


# ---------------------------------------------------------------------------
# 16.4 — retry_failed_emails Celery beat task
# ---------------------------------------------------------------------------

class RetryFailedEmailsTaskTest(TestCase):
    """Retry logic: retries up to 3 times, stops after 3 failures."""

    def setUp(self):
        self.auditor = make_user("auditor5", UserRole.AUDITOR)
        self.tender = make_tender()
        AlertSettings.objects.create(user=self.auditor, category="", email_enabled=True, threshold=70)

    def _make_failed_alert(self, retry_count=0):
        return Alert.objects.create(
            tender=self.tender,
            user=self.auditor,
            title=self.tender.title,
            detail_link=f"/tenders/{self.tender.pk}",
            fraud_risk_score=80,
            top_red_flags=[],
            delivery_status=DeliveryStatus.FAILED,
            retry_count=retry_count,
        )

    @patch("alerts.tasks.send_mail")
    def test_retry_succeeds_on_second_attempt(self, mock_send_mail):
        """Retry succeeds: delivery_status becomes DELIVERED."""
        alert = self._make_failed_alert(retry_count=0)
        retry_failed_emails()
        alert.refresh_from_db()
        self.assertEqual(alert.delivery_status, DeliveryStatus.DELIVERED)
        self.assertEqual(alert.retry_count, 1)

    @patch("alerts.tasks.send_mail", side_effect=Exception("SMTP error"))
    def test_retry_increments_retry_count(self, mock_send_mail):
        """Each failed retry increments retry_count."""
        alert = self._make_failed_alert(retry_count=0)
        retry_failed_emails()
        alert.refresh_from_db()
        self.assertEqual(alert.retry_count, 1)
        self.assertEqual(alert.delivery_status, DeliveryStatus.FAILED)

    @patch("alerts.tasks.send_mail", side_effect=Exception("SMTP error"))
    def test_permanently_failed_after_max_retries(self, mock_send_mail):
        """After MAX_RETRY_COUNT failures, status becomes PERMANENTLY_FAILED."""
        alert = self._make_failed_alert(retry_count=MAX_RETRY_COUNT - 1)
        retry_failed_emails()
        alert.refresh_from_db()
        self.assertEqual(alert.delivery_status, DeliveryStatus.PERMANENTLY_FAILED)
        self.assertEqual(alert.retry_count, MAX_RETRY_COUNT)

    @patch("alerts.tasks.send_mail")
    def test_no_retry_when_max_retries_reached(self, mock_send_mail):
        """Alerts with retry_count >= MAX_RETRY_COUNT are not retried."""
        alert = self._make_failed_alert(retry_count=MAX_RETRY_COUNT)
        retry_failed_emails()
        mock_send_mail.assert_not_called()

    @patch("alerts.tasks.send_mail", side_effect=Exception("SMTP error"))
    def test_audit_log_written_on_retry_failure(self, mock_send_mail):
        """AuditLog entry written on each failed retry."""
        alert = self._make_failed_alert(retry_count=0)
        retry_failed_emails()
        self.assertTrue(
            AuditLog.objects.filter(
                event_type="ALERT_FAILED",
                affected_entity_id=str(alert.pk),
            ).exists()
        )


# ---------------------------------------------------------------------------
# 16.5 — Alert API endpoints
# ---------------------------------------------------------------------------

class AlertListEndpointTest(TestCase):
    """GET /api/v1/alerts/ — list alerts for authenticated user, last 90 days."""

    def setUp(self):
        self.client = APIClient()
        self.auditor = make_user("auditor6", UserRole.AUDITOR)
        self.tender = make_tender()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {get_jwt(self.auditor)}")

    def _make_alert(self, days_ago=0):
        created = timezone.now() - timedelta(days=days_ago)
        alert = Alert.objects.create(
            tender=self.tender,
            user=self.auditor,
            title=self.tender.title,
            detail_link=f"/tenders/{self.tender.pk}",
            fraud_risk_score=80,
            top_red_flags=[],
            delivery_status=DeliveryStatus.PENDING,
        )
        # Override created_at
        Alert.objects.filter(pk=alert.pk).update(created_at=created)
        return alert

    def test_list_returns_alerts_within_90_days(self):
        """Alerts within 90 days are returned."""
        self._make_alert(days_ago=0)
        self._make_alert(days_ago=45)
        response = self.client.get("/api/v1/alerts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 2)

    def test_90_day_filter_excludes_old_alerts(self):
        """Alerts older than 90 days are excluded."""
        self._make_alert(days_ago=0)
        self._make_alert(days_ago=91)  # older than 90 days
        response = self.client.get("/api/v1/alerts/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

    def test_list_only_returns_own_alerts(self):
        """Users only see their own alerts."""
        other_user = make_user("other_auditor", UserRole.AUDITOR)
        Alert.objects.create(
            tender=self.tender,
            user=other_user,
            title="Other",
            detail_link="/tenders/1",
            fraud_risk_score=80,
            top_red_flags=[],
        )
        self._make_alert()
        response = self.client.get("/api/v1/alerts/")
        self.assertEqual(response.data["count"], 1)

    def test_unauthenticated_returns_401(self):
        """Unauthenticated requests return 401."""
        self.client.credentials()
        response = self.client.get("/api/v1/alerts/")
        self.assertEqual(response.status_code, 401)


class AlertDetailEndpointTest(TestCase):
    """GET /api/v1/alerts/{id}/ — alert detail."""

    def setUp(self):
        self.client = APIClient()
        self.auditor = make_user("auditor7", UserRole.AUDITOR)
        self.tender = make_tender()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {get_jwt(self.auditor)}")
        self.alert = Alert.objects.create(
            tender=self.tender,
            user=self.auditor,
            title=self.tender.title,
            detail_link=f"/tenders/{self.tender.pk}",
            fraud_risk_score=80,
            top_red_flags=[{"flag_type": "SINGLE_BIDDER", "severity": "HIGH"}],
        )

    def test_detail_returns_alert(self):
        response = self.client.get(f"/api/v1/alerts/{self.alert.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.alert.pk)
        self.assertEqual(response.data["fraud_risk_score"], 80)

    def test_detail_returns_404_for_other_user_alert(self):
        other = make_user("other8", UserRole.AUDITOR)
        other_alert = Alert.objects.create(
            tender=self.tender,
            user=other,
            title="Other",
            detail_link="/tenders/1",
            fraud_risk_score=80,
            top_red_flags=[],
        )
        response = self.client.get(f"/api/v1/alerts/{other_alert.pk}/")
        self.assertEqual(response.status_code, 404)


class AlertUnreadEndpointTest(TestCase):
    """GET /api/v1/alerts/unread/ — unread alerts, marks them as read."""

    def setUp(self):
        self.client = APIClient()
        self.auditor = make_user("auditor9", UserRole.AUDITOR)
        self.tender = make_tender()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {get_jwt(self.auditor)}")

    def _make_alert(self, is_read=False):
        return Alert.objects.create(
            tender=self.tender,
            user=self.auditor,
            title=self.tender.title,
            detail_link=f"/tenders/{self.tender.pk}",
            fraud_risk_score=80,
            top_red_flags=[],
            is_read=is_read,
        )

    def test_unread_returns_only_unread_alerts(self):
        self._make_alert(is_read=False)
        self._make_alert(is_read=True)
        response = self.client.get("/api/v1/alerts/unread/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_unread_marks_alerts_as_read(self):
        alert = self._make_alert(is_read=False)
        self.client.get("/api/v1/alerts/unread/")
        alert.refresh_from_db()
        self.assertTrue(alert.is_read)


class AlertMarkReadEndpointTest(TestCase):
    """POST /api/v1/alerts/{id}/read/ — mark alert as read."""

    def setUp(self):
        self.client = APIClient()
        self.auditor = make_user("auditor10", UserRole.AUDITOR)
        self.tender = make_tender()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {get_jwt(self.auditor)}")
        self.alert = Alert.objects.create(
            tender=self.tender,
            user=self.auditor,
            title=self.tender.title,
            detail_link=f"/tenders/{self.tender.pk}",
            fraud_risk_score=80,
            top_red_flags=[],
            is_read=False,
        )

    def test_mark_read_sets_is_read(self):
        response = self.client.post(f"/api/v1/alerts/{self.alert.pk}/read/")
        self.assertEqual(response.status_code, 200)
        self.alert.refresh_from_db()
        self.assertTrue(self.alert.is_read)

    def test_mark_read_returns_404_for_other_user(self):
        other = make_user("other11", UserRole.AUDITOR)
        other_alert = Alert.objects.create(
            tender=self.tender,
            user=other,
            title="Other",
            detail_link="/tenders/1",
            fraud_risk_score=80,
            top_red_flags=[],
        )
        response = self.client.post(f"/api/v1/alerts/{other_alert.pk}/read/")
        self.assertEqual(response.status_code, 404)


class AlertSettingsEndpointTest(TestCase):
    """POST/GET /api/v1/alerts/settings/ — ADMIN only."""

    def setUp(self):
        self.client = APIClient()
        self.admin = make_user("admin12", UserRole.ADMIN)
        self.auditor = make_user("auditor12", UserRole.AUDITOR)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {get_jwt(self.admin)}")

    def test_admin_can_create_settings(self):
        response = self.client.post(
            "/api/v1/alerts/settings/",
            {"threshold": 80, "category": "", "email_enabled": True},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["threshold"], 80)

    def test_admin_can_update_settings(self):
        AlertSettings.objects.create(user=self.admin, category="", threshold=70)
        response = self.client.post(
            "/api/v1/alerts/settings/",
            {"threshold": 85, "category": "", "email_enabled": False},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["threshold"], 85)

    def test_admin_can_get_settings(self):
        AlertSettings.objects.create(user=self.admin, category="", threshold=70)
        response = self.client.get("/api/v1/alerts/settings/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_auditor_cannot_access_settings(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {get_jwt(self.auditor)}")
        response = self.client.get("/api/v1/alerts/settings/")
        self.assertEqual(response.status_code, 403)

    def test_invalid_threshold_rejected(self):
        response = self.client.post(
            "/api/v1/alerts/settings/",
            {"threshold": 150, "category": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
