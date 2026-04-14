"""
Unit tests for XAIExplainer (backend/xai/explainer.py).

Covers:
  - explain() assembles top-5 plain-language factors correctly
  - explain() includes all active RedFlags with rule text and trigger data
  - fallback_explain() returns red-flag-only explanation when shap_failed=True
  - Response latency: explanation assembled within 3 seconds (Requirement 6.3)
  - Version stamps are present in explanation output (Requirement 6.5)
  - AuditLog entry is written on explanation generation
"""

import time
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from audit.models import AuditLog, EventType
from authentication.models import User
from detection.models import FlagType, RedFlag, RuleDefinition, Severity
from tenders.models import Tender
from xai.explainer import XAIExplainer, _render_template
from xai.models import SHAPExplanation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FEATURE_COLUMNS = [
    "cv_bids",
    "bid_spread_ratio",
    "norm_winning_distance",
    "single_bidder_flag",
    "price_deviation_pct",
    "deadline_days",
    "repeat_winner_rate",
    "bidder_count",
    "winner_bid_rank",
]


def _make_tender(**kwargs) -> Tender:
    defaults = {
        "tender_id": "T-001",
        "title": "Test Tender",
        "category": "IT",
        "estimated_value": "100000.00",
        "currency": "INR",
        "submission_deadline": timezone.now() + timedelta(days=30),
        "buyer_id": "B-001",
        "buyer_name": "Test Buyer",
    }
    defaults.update(kwargs)
    return Tender.objects.create(**defaults)


def _make_shap_values(seed: int = 0) -> dict:
    """Return deterministic SHAP values for all 9 features."""
    import hashlib
    result = {}
    for i, col in enumerate(FEATURE_COLUMNS):
        h = int(hashlib.md5(f"{seed}-{col}".encode()).hexdigest(), 16)
        result[col] = ((h % 2000) - 1000) / 1000.0  # range [-1, 1]
    return result


def _make_top_factors(shap_values: dict, n: int = 5) -> list:
    """Build top_factors list sorted by |SHAP| descending."""
    sorted_features = sorted(FEATURE_COLUMNS, key=lambda f: abs(shap_values[f]), reverse=True)
    return [
        {
            "feature": f,
            "shap_value": shap_values[f],
            "feature_value": 0.5,
            "explanation": "",
        }
        for f in sorted_features[:n]
    ]


def _make_shap_explanation(tender: Tender, shap_failed: bool = False, **kwargs) -> SHAPExplanation:
    shap_values = _make_shap_values()
    top_factors = [] if shap_failed else _make_top_factors(shap_values)
    defaults = {
        "tender": tender,
        "model_version": "RF:v1",
        "rule_engine_version": "1.0",
        "shap_values": {} if shap_failed else shap_values,
        "top_factors": top_factors,
        "shap_failed": shap_failed,
    }
    defaults.update(kwargs)
    return SHAPExplanation.objects.create(**defaults)


def _make_rule_definition(rule_code: str, description: str = "", severity: str = Severity.HIGH) -> RuleDefinition:
    return RuleDefinition.objects.create(
        rule_code=rule_code,
        description=description or f"Rule: {rule_code}",
        severity=severity,
        is_active=True,
        parameters={},
    )


def _make_red_flag(tender: Tender, flag_type: str = FlagType.SINGLE_BIDDER,
                   severity: str = Severity.HIGH, trigger_data: dict | None = None) -> RedFlag:
    return RedFlag.objects.create(
        tender=tender,
        flag_type=flag_type,
        severity=severity,
        rule_version="1.0",
        trigger_data=trigger_data or {"bid_count": 1},
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Tests: explain() — top-5 plain-language factors
# ---------------------------------------------------------------------------

class TestExplainTopFactors(TestCase):
    """explain() must assemble top-5 plain-language factors from SHAPExplanation."""

    def setUp(self):
        self.tender = _make_tender()
        self.shap_exp = _make_shap_explanation(self.tender)
        self.explainer = XAIExplainer()

    def test_top_factors_has_at_most_five_entries(self):
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertLessEqual(len(result["top_factors"]), 5)

    def test_top_factors_each_have_explanation_sentence(self):
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        for factor in result["top_factors"]:
            self.assertIn("explanation", factor)
            self.assertIsInstance(factor["explanation"], str)
            self.assertGreater(len(factor["explanation"]), 0)

    def test_top_factors_each_have_required_keys(self):
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        for factor in result["top_factors"]:
            self.assertIn("feature", factor)
            self.assertIn("shap_value", factor)
            self.assertIn("feature_value", factor)
            self.assertIn("explanation", factor)

    def test_top_factors_feature_names_are_valid(self):
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        for factor in result["top_factors"]:
            self.assertIn(factor["feature"], FEATURE_COLUMNS)

    def test_shap_failed_false_in_normal_explain(self):
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertFalse(result["shap_failed"])

    def test_shap_values_present_in_normal_explain(self):
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertIsInstance(result["shap_values"], dict)
        self.assertGreater(len(result["shap_values"]), 0)

    def test_explain_returns_tender_id(self):
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertEqual(result["tender_id"], self.tender.pk)


# ---------------------------------------------------------------------------
# Tests: explain() — red flags with rule text and trigger data
# ---------------------------------------------------------------------------

class TestExplainRedFlags(TestCase):
    """explain() must include all active RedFlags with rule text and trigger data."""

    def setUp(self):
        self.tender = _make_tender()
        _make_shap_explanation(self.tender)
        self.explainer = XAIExplainer()

    def test_red_flags_included_in_explanation(self):
        _make_rule_definition(FlagType.SINGLE_BIDDER, "Only one bidder submitted a bid.")
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER, trigger_data={"bid_count": 1})

        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertEqual(len(result["red_flags"]), 1)

    def test_red_flag_has_rule_text(self):
        rule_desc = "Only one bidder submitted a bid."
        _make_rule_definition(FlagType.SINGLE_BIDDER, rule_desc)
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER)

        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        flag = result["red_flags"][0]
        self.assertEqual(flag["rule_text"], rule_desc)

    def test_red_flag_has_trigger_data(self):
        _make_rule_definition(FlagType.SINGLE_BIDDER)
        trigger = {"bid_count": 1, "extra": "data"}
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER, trigger_data=trigger)

        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        flag = result["red_flags"][0]
        self.assertEqual(flag["trigger_data"], trigger)

    def test_all_active_red_flags_included(self):
        _make_rule_definition(FlagType.SINGLE_BIDDER)
        _make_rule_definition(FlagType.PRICE_ANOMALY, severity=Severity.MEDIUM)
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER)
        _make_red_flag(self.tender, FlagType.PRICE_ANOMALY, severity=Severity.MEDIUM)

        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertEqual(len(result["red_flags"]), 2)

    def test_inactive_red_flags_excluded(self):
        _make_rule_definition(FlagType.SINGLE_BIDDER)
        active_flag = _make_red_flag(self.tender, FlagType.SINGLE_BIDDER)
        # Create an inactive flag
        RedFlag.objects.create(
            tender=self.tender,
            flag_type=FlagType.PRICE_ANOMALY,
            severity=Severity.MEDIUM,
            rule_version="1.0",
            trigger_data={"deviation_pct": 50},
            is_active=False,
        )

        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertEqual(len(result["red_flags"]), 1)
        self.assertEqual(result["red_flags"][0]["flag_type"], FlagType.SINGLE_BIDDER)

    def test_red_flag_has_required_keys(self):
        _make_rule_definition(FlagType.SINGLE_BIDDER)
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER)

        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        flag = result["red_flags"][0]
        for key in ("id", "flag_type", "severity", "rule_version", "trigger_data", "raised_at", "rule_text"):
            self.assertIn(key, flag)

    def test_no_red_flags_returns_empty_list(self):
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertEqual(result["red_flags"], [])


# ---------------------------------------------------------------------------
# Tests: fallback_explain() — red-flag-only explanation
# ---------------------------------------------------------------------------

class TestFallbackExplain(TestCase):
    """fallback_explain() must return red-flag-only explanation."""

    def setUp(self):
        self.tender = _make_tender()
        self.explainer = XAIExplainer()

    def test_fallback_shap_failed_is_true(self):
        result = self.explainer.fallback_explain(self.tender.pk)
        self.assertTrue(result["shap_failed"])

    def test_fallback_shap_values_empty(self):
        result = self.explainer.fallback_explain(self.tender.pk)
        self.assertEqual(result["shap_values"], {})

    def test_fallback_top_factors_empty(self):
        result = self.explainer.fallback_explain(self.tender.pk)
        self.assertEqual(result["top_factors"], [])

    def test_fallback_includes_active_red_flags(self):
        _make_rule_definition(FlagType.SINGLE_BIDDER)
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER)

        result = self.explainer.fallback_explain(self.tender.pk)
        self.assertEqual(len(result["red_flags"]), 1)

    def test_fallback_red_flag_has_rule_text(self):
        rule_desc = "Single bidder detected."
        _make_rule_definition(FlagType.SINGLE_BIDDER, rule_desc)
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER)

        result = self.explainer.fallback_explain(self.tender.pk)
        self.assertEqual(result["red_flags"][0]["rule_text"], rule_desc)

    def test_explain_delegates_to_fallback_when_shap_failed(self):
        """explain() must call fallback when SHAPExplanation.shap_failed=True."""
        _make_shap_explanation(self.tender, shap_failed=True)
        _make_rule_definition(FlagType.SINGLE_BIDDER)
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER)

        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertTrue(result["shap_failed"])
        self.assertEqual(result["shap_values"], {})
        self.assertEqual(result["top_factors"], [])
        self.assertEqual(len(result["red_flags"]), 1)

    def test_explain_delegates_to_fallback_when_no_shap_explanation(self):
        """explain() must call fallback when no SHAPExplanation exists."""
        _make_rule_definition(FlagType.SINGLE_BIDDER)
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER)

        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertTrue(result["shap_failed"])

    def test_fallback_returns_tender_id(self):
        result = self.explainer.fallback_explain(self.tender.pk)
        self.assertEqual(result["tender_id"], self.tender.pk)

    def test_fallback_nonexistent_tender_returns_error(self):
        result = self.explainer.fallback_explain(99999)
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Tests: version stamps
# ---------------------------------------------------------------------------

class TestVersionStamps(TestCase):
    """Explanation must include model_version and rule_engine_version (Requirement 6.5)."""

    def setUp(self):
        self.tender = _make_tender()
        self.explainer = XAIExplainer()

    def test_model_version_present_in_explanation(self):
        _make_shap_explanation(self.tender, model_version="RF:v2")
        result = self.explainer.explain(self.tender.pk, model_version="RF:v2")
        self.assertEqual(result["model_version"], "RF:v2")

    def test_rule_engine_version_present_in_explanation(self):
        _make_shap_explanation(self.tender, rule_engine_version="2.5")
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertEqual(result["rule_engine_version"], "2.5")

    def test_version_stamps_present_in_fallback(self):
        _make_shap_explanation(self.tender, shap_failed=True, model_version="RF:v3", rule_engine_version="3.0")
        result = self.explainer.fallback_explain(self.tender.pk)
        self.assertEqual(result["model_version"], "RF:v3")
        self.assertEqual(result["rule_engine_version"], "3.0")

    def test_computed_at_present_in_explanation(self):
        _make_shap_explanation(self.tender)
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertIsNotNone(result["computed_at"])


# ---------------------------------------------------------------------------
# Tests: AuditLog entry written
# ---------------------------------------------------------------------------

class TestAuditLogEntry(TestCase):
    """An EXPLANATION_GENERATED AuditLog entry must be written on each explain() call."""

    def setUp(self):
        self.tender = _make_tender()
        self.explainer = XAIExplainer()

    def test_audit_log_created_on_explain(self):
        _make_shap_explanation(self.tender)
        before_count = AuditLog.objects.count()
        self.explainer.explain(self.tender.pk, model_version="RF:v1")
        self.assertEqual(AuditLog.objects.count(), before_count + 1)

    def test_audit_log_event_type_is_explanation_generated(self):
        _make_shap_explanation(self.tender)
        self.explainer.explain(self.tender.pk, model_version="RF:v1")
        log = AuditLog.objects.order_by("-timestamp").first()
        self.assertEqual(log.event_type, EventType.EXPLANATION_GENERATED)

    def test_audit_log_references_tender(self):
        _make_shap_explanation(self.tender)
        self.explainer.explain(self.tender.pk, model_version="RF:v1")
        log = AuditLog.objects.order_by("-timestamp").first()
        self.assertEqual(log.affected_entity_type, "Tender")
        self.assertEqual(log.affected_entity_id, self.tender.tender_id)

    def test_audit_log_snapshot_contains_model_version(self):
        _make_shap_explanation(self.tender, model_version="RF:v7")
        self.explainer.explain(self.tender.pk, model_version="RF:v7")
        log = AuditLog.objects.order_by("-timestamp").first()
        self.assertEqual(log.data_snapshot["model_version"], "RF:v7")

    def test_audit_log_created_on_fallback(self):
        before_count = AuditLog.objects.count()
        self.explainer.fallback_explain(self.tender.pk)
        self.assertEqual(AuditLog.objects.count(), before_count + 1)


# ---------------------------------------------------------------------------
# Tests: Response latency (Requirement 6.3 — within 3 seconds)
# ---------------------------------------------------------------------------

class TestResponseLatency(TestCase):
    """Explanation must be assembled within 3 seconds (Requirement 6.3)."""

    def setUp(self):
        self.tender = _make_tender()
        self.explainer = XAIExplainer()

    def test_explain_completes_within_3_seconds(self):
        _make_shap_explanation(self.tender)
        # Add a few red flags to simulate realistic load
        for flag_type in [FlagType.SINGLE_BIDDER, FlagType.PRICE_ANOMALY, FlagType.SHORT_DEADLINE]:
            _make_rule_definition(flag_type)
            _make_red_flag(self.tender, flag_type)

        start = time.monotonic()
        result = self.explainer.explain(self.tender.pk, model_version="RF:v1")
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 3.0, f"explain() took {elapsed:.2f}s, exceeds 3s limit")
        self.assertNotIn("error", result)

    def test_fallback_explain_completes_within_3_seconds(self):
        for flag_type in [FlagType.SINGLE_BIDDER, FlagType.PRICE_ANOMALY]:
            _make_rule_definition(flag_type)
            _make_red_flag(self.tender, flag_type)

        start = time.monotonic()
        result = self.explainer.fallback_explain(self.tender.pk)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 3.0, f"fallback_explain() took {elapsed:.2f}s, exceeds 3s limit")
        self.assertTrue(result["shap_failed"])


# ---------------------------------------------------------------------------
# Tests: _render_template unit tests
# ---------------------------------------------------------------------------

class TestRenderTemplate(TestCase):
    """Unit tests for the plain-language template renderer."""

    def test_price_deviation_below(self):
        sentence = _render_template("price_deviation_pct", -0.52)
        self.assertIn("52%", sentence)
        self.assertIn("below", sentence)

    def test_price_deviation_above(self):
        sentence = _render_template("price_deviation_pct", 0.30)
        self.assertIn("30%", sentence)
        self.assertIn("above", sentence)

    def test_bidder_count(self):
        sentence = _render_template("bidder_count", 1.0)
        self.assertIn("1", sentence)
        self.assertIn("bidder", sentence)

    def test_single_bidder_flag(self):
        sentence = _render_template("single_bidder_flag", 1.0)
        self.assertIn("single bidder", sentence.lower())

    def test_repeat_winner_rate(self):
        sentence = _render_template("repeat_winner_rate", 0.75)
        self.assertIn("75%", sentence)

    def test_deadline_days(self):
        sentence = _render_template("deadline_days", 2.0)
        self.assertIn("2", sentence)
        self.assertIn("day", sentence)

    def test_winner_bid_rank_first(self):
        sentence = _render_template("winner_bid_rank", 1.0)
        self.assertIn("1st", sentence)

    def test_winner_bid_rank_second(self):
        sentence = _render_template("winner_bid_rank", 2.0)
        self.assertIn("2nd", sentence)

    def test_unknown_feature_fallback(self):
        sentence = _render_template("unknown_feature_xyz", 0.42)
        self.assertIn("unknown_feature_xyz", sentence)

    def test_cv_bids_close_together(self):
        sentence = _render_template("cv_bids", 0.05)
        self.assertIn("close together", sentence)

    def test_cv_bids_spread_out(self):
        sentence = _render_template("cv_bids", 0.5)
        self.assertIn("spread out", sentence)


# ---------------------------------------------------------------------------
# Tests: API endpoint integration
# ---------------------------------------------------------------------------

class TestExplanationEndpoint(TestCase):
    """Integration tests for GET /api/v1/tenders/{id}/explanation/."""

    def setUp(self):
        from django.test import Client
        from rest_framework_simplejwt.tokens import AccessToken

        self.client = Client()
        self.user = User.objects.create_user(
            username="auditor1",
            email="auditor1@example.com",
            password="testpass123",
            role="AUDITOR",
        )
        token = AccessToken.for_user(self.user)
        self.auth_header = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        self.tender = _make_tender()

    def test_explanation_endpoint_returns_200_with_shap(self):
        _make_shap_explanation(self.tender)
        response = self.client.get(
            f"/api/v1/tenders/{self.tender.pk}/explanation/",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 200)

    def test_explanation_endpoint_returns_shap_failed_true_on_fallback(self):
        _make_shap_explanation(self.tender, shap_failed=True)
        response = self.client.get(
            f"/api/v1/tenders/{self.tender.pk}/explanation/",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["shap_failed"])

    def test_explanation_endpoint_returns_404_for_unknown_tender(self):
        response = self.client.get(
            "/api/v1/tenders/99999/explanation/",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 404)

    def test_explanation_endpoint_requires_auth(self):
        response = self.client.get(f"/api/v1/tenders/{self.tender.pk}/explanation/")
        self.assertEqual(response.status_code, 401)

    def test_explanation_endpoint_response_within_3_seconds(self):
        _make_shap_explanation(self.tender)
        start = time.monotonic()
        response = self.client.get(
            f"/api/v1/tenders/{self.tender.pk}/explanation/",
            **self.auth_header,
        )
        elapsed = time.monotonic() - start
        self.assertEqual(response.status_code, 200)
        self.assertLess(elapsed, 3.0, f"Endpoint took {elapsed:.2f}s, exceeds 3s limit")

    def test_explanation_endpoint_includes_red_flags(self):
        _make_shap_explanation(self.tender)
        _make_rule_definition(FlagType.SINGLE_BIDDER, "Single bidder rule.")
        _make_red_flag(self.tender, FlagType.SINGLE_BIDDER)

        response = self.client.get(
            f"/api/v1/tenders/{self.tender.pk}/explanation/",
            **self.auth_header,
        )
        data = response.json()
        self.assertEqual(len(data["red_flags"]), 1)
        self.assertEqual(data["red_flags"][0]["rule_text"], "Single bidder rule.")

    def test_explanation_endpoint_no_shap_returns_fallback(self):
        """When no SHAPExplanation exists, endpoint returns fallback (shap_failed=True)."""
        response = self.client.get(
            f"/api/v1/tenders/{self.tender.pk}/explanation/",
            **self.auth_header,
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["shap_failed"])
