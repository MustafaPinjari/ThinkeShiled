# Feature: tender-shield, Property 17: Alert Threshold Firing
#
# For any tender whose score reaches or exceeds the configured threshold
# (global or per-category), Alert records are created for all AUDITOR and
# ADMIN users, each containing tender_id, title, score, top 3 RedFlags,
# and a detail page link. When score < threshold, no Alert records are created.
# Validates: Requirements 10.1, 10.3, 10.6

from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

from alerts.alert_system import AlertSystem
from alerts.models import Alert, AlertSettings
from authentication.models import User, UserRole
from detection.models import FlagType, RedFlag, Severity
from scoring.models import FraudRiskScore
from tenders.models import Tender

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


def _uid():
    global _counter
    _counter += 1
    return _counter


def _make_tender(category="IT"):
    uid = _uid()
    return Tender.objects.create(
        tender_id=f"PBT-ALERT-{uid}",
        title=f"PBT Alert Tender {uid}",
        category=category,
        estimated_value=Decimal("100000.00"),
        currency="INR",
        submission_deadline=timezone.now() + timezone.timedelta(days=30),
        buyer_id="PBT-BUYER",
        buyer_name="PBT Buyer",
    )


def _make_user(role, suffix=""):
    uid = _uid()
    return User.objects.create_user(
        username=f"pbt-{role.lower()}-{uid}{suffix}",
        email=f"pbt-{role.lower()}-{uid}{suffix}@test.com",
        password="testpass",
        role=role,
    )


def _make_score(tender, score):
    return FraudRiskScore.objects.create(
        tender=tender,
        score=score,
        computed_at=timezone.now(),
    )


def _make_red_flag(tender, flag_type=FlagType.SINGLE_BIDDER, severity=Severity.HIGH):
    return RedFlag.objects.create(
        tender=tender,
        flag_type=flag_type,
        severity=severity,
        trigger_data={},
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Property 17a — Global threshold: alerts fire iff score >= threshold
# ---------------------------------------------------------------------------

class AlertThresholdFiringGlobalTest(TestCase):
    """
    Property 17: Alert Threshold Firing (global threshold).
    Validates: Requirements 10.1, 10.3
    """

    @given(
        score=st.integers(min_value=0, max_value=100),
        threshold=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_alerts_fire_when_score_meets_or_exceeds_global_threshold(self, score, threshold):
        # Feature: tender-shield, Property 17: Alert Threshold Firing
        with patch("alerts.tasks.send_alert_email.delay"):
            auditor = _make_user(UserRole.AUDITOR)
            admin = _make_user(UserRole.ADMIN)

            tender = _make_tender()
            _make_score(tender, score)

            # Set global threshold (category="")
            AlertSettings.objects.create(
                user=auditor,
                category="",
                threshold=threshold,
            )

            system = AlertSystem()
            alerts = system.check_and_alert(tender.pk)

        if score >= threshold:
            # Alerts must be created for ALL AUDITOR and ADMIN users
            assert len(alerts) == 2, (
                f"Expected 2 alerts (auditor + admin) when score={score} >= threshold={threshold}, "
                f"got {len(alerts)}"
            )
            user_ids = {a.user_id for a in alerts}
            assert auditor.pk in user_ids, "Auditor must receive an alert"
            assert admin.pk in user_ids, "Admin must receive an alert"
        else:
            # No alerts when score < threshold
            assert len(alerts) == 0, (
                f"Expected 0 alerts when score={score} < threshold={threshold}, "
                f"got {len(alerts)}"
            )

    @given(
        score=st.integers(min_value=0, max_value=100),
        threshold=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_alert_content_fields_present_when_threshold_met(self, score, threshold):
        # Feature: tender-shield, Property 17: Alert Threshold Firing — content fields
        # Only test content when score >= threshold
        if score < threshold:
            return

        with patch("alerts.tasks.send_alert_email.delay"):
            auditor = _make_user(UserRole.AUDITOR)
            _make_user(UserRole.ADMIN)  # ensure admin exists

            tender = _make_tender()
            _make_score(tender, score)

            # Add up to 4 red flags so we can verify top-3 capping
            _make_red_flag(tender, FlagType.SINGLE_BIDDER, Severity.HIGH)
            _make_red_flag(tender, FlagType.PRICE_ANOMALY, Severity.MEDIUM)
            _make_red_flag(tender, FlagType.REPEAT_WINNER, Severity.HIGH)
            _make_red_flag(tender, FlagType.SHORT_DEADLINE, Severity.MEDIUM)

            AlertSettings.objects.create(
                user=auditor,
                category="",
                threshold=threshold,
            )

            system = AlertSystem()
            alerts = system.check_and_alert(tender.pk)

        assert len(alerts) >= 1

        for alert in alerts:
            # Req 10.3: tender_id, title, score, top 3 red flags, detail link
            assert alert.tender_id == tender.pk, "Alert must reference the correct tender"
            assert alert.title == tender.title, "Alert title must match tender title"
            assert alert.fraud_risk_score == score, "Alert score must match the fraud risk score"
            assert alert.detail_link == f"/tenders/{tender.pk}", "Alert must contain detail page link"
            assert len(alert.top_red_flags) <= 3, "Alert must contain at most 3 red flags"
            assert len(alert.top_red_flags) == 3, "Alert must contain exactly top 3 red flags when 4 exist"


# ---------------------------------------------------------------------------
# Property 17b — Per-category threshold (Requirement 10.6)
# ---------------------------------------------------------------------------

class AlertThresholdFiringPerCategoryTest(TestCase):
    """
    Property 17: Alert Threshold Firing (per-category threshold).
    Validates: Requirements 10.1, 10.6
    """

    @given(
        score=st.integers(min_value=0, max_value=100),
        global_threshold=st.integers(min_value=0, max_value=100),
        category_threshold=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much], deadline=None)
    def test_category_threshold_takes_precedence_over_global(
        self, score, global_threshold, category_threshold
    ):
        # Feature: tender-shield, Property 17: Alert Threshold Firing — per-category
        category = "Construction"

        with patch("alerts.tasks.send_alert_email.delay"):
            auditor = _make_user(UserRole.AUDITOR)
            _make_user(UserRole.ADMIN)

            tender = _make_tender(category=category)
            _make_score(tender, score)

            # Set both global and per-category thresholds
            AlertSettings.objects.create(
                user=auditor,
                category="",
                threshold=global_threshold,
            )
            AlertSettings.objects.create(
                user=auditor,
                category=category,
                threshold=category_threshold,
            )

            system = AlertSystem()
            alerts = system.check_and_alert(tender.pk)

        # Per-category threshold must be used (not global)
        if score >= category_threshold:
            assert len(alerts) >= 1, (
                f"Expected alerts when score={score} >= category_threshold={category_threshold} "
                f"(global={global_threshold}), got {len(alerts)}"
            )
        else:
            assert len(alerts) == 0, (
                f"Expected no alerts when score={score} < category_threshold={category_threshold} "
                f"(global={global_threshold}), got {len(alerts)}"
            )

    @given(
        score=st.integers(min_value=0, max_value=100),
        threshold=st.integers(min_value=0, max_value=100),
    )
    @settings(max_examples=25, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_all_auditor_and_admin_users_receive_alert_on_category_threshold(
        self, score, threshold
    ):
        # Feature: tender-shield, Property 17: Alert Threshold Firing — all recipients
        if score < threshold:
            return

        category = "Healthcare"

        with patch("alerts.tasks.send_alert_email.delay"):
            # Create multiple auditors and admins
            auditor1 = _make_user(UserRole.AUDITOR)
            auditor2 = _make_user(UserRole.AUDITOR)
            admin1 = _make_user(UserRole.ADMIN)

            tender = _make_tender(category=category)
            _make_score(tender, score)

            AlertSettings.objects.create(
                user=auditor1,
                category=category,
                threshold=threshold,
            )

            system = AlertSystem()
            alerts = system.check_and_alert(tender.pk)

        # All 3 active AUDITOR/ADMIN users must receive alerts
        assert len(alerts) == 3, (
            f"Expected 3 alerts (2 auditors + 1 admin) when score={score} >= threshold={threshold}, "
            f"got {len(alerts)}"
        )
        user_ids = {a.user_id for a in alerts}
        assert auditor1.pk in user_ids
        assert auditor2.pk in user_ids
        assert admin1.pk in user_ids
