"""
Unit tests for RiskScorer — covers:
  - Scoring formula at boundary values
  - Clamping to [0, 100]
  - Custom weight application
  - Score persistence and AuditLog creation
  - get_score() returns latest row
  - ML-null fallback (rule-only mode)

Property 10 (PBT) lives in backend/tests/test_scoring.py.
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from scoring.scorer import RiskScorer, ScoringWeights, DEFAULT_HIGH_WEIGHT, DEFAULT_MEDIUM_WEIGHT


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _make_tender(db):
    """Create a minimal Tender for testing."""
    from tenders.models import Tender
    return Tender.objects.create(
        tender_id=f"T-{timezone.now().timestamp()}",
        title="Test Tender",
        category="Construction",
        estimated_value=Decimal("100000.00"),
        currency="INR",
        submission_deadline=timezone.now() + timezone.timedelta(days=10),
        buyer_id="B001",
        buyer_name="Test Buyer",
    )


def _make_red_flag(tender, severity):
    """Create an active RedFlag for testing."""
    from detection.models import RedFlag, FlagType
    return RedFlag.objects.create(
        tender=tender,
        flag_type=FlagType.SINGLE_BIDDER,
        severity=severity,
        rule_version="1",
        trigger_data={},
        is_active=True,
    )


# ------------------------------------------------------------------ #
# Formula tests                                                        #
# ------------------------------------------------------------------ #

class ScoringFormulaTest(TestCase):
    """Tests for the scoring formula with known inputs."""

    def setUp(self):
        self.tender = _make_tender(self)
        self.scorer = RiskScorer()

    def test_no_flags_no_ml_scores_zero(self):
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertEqual(score_record.score, 0)

    def test_single_high_flag_no_ml(self):
        _make_red_flag(self.tender, "HIGH")
        score_record = self.scorer.compute_score(self.tender.pk)
        # HIGH × 25 = 25; no ML
        self.assertEqual(score_record.score, 25)

    def test_single_medium_flag_no_ml(self):
        _make_red_flag(self.tender, "MEDIUM")
        score_record = self.scorer.compute_score(self.tender.pk)
        # MEDIUM × 10 = 10; no ML
        self.assertEqual(score_record.score, 10)

    def test_two_high_flags_no_ml(self):
        _make_red_flag(self.tender, "HIGH")
        _make_red_flag(self.tender, "HIGH")
        score_record = self.scorer.compute_score(self.tender.pk)
        # 2 × 25 = 50; no ML
        self.assertEqual(score_record.score, 50)

    def test_red_flag_cap_at_50(self):
        """3 HIGH flags = 75 raw, but capped at 50."""
        for _ in range(3):
            _make_red_flag(self.tender, "HIGH")
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertEqual(score_record.red_flag_contribution, 50)
        self.assertEqual(score_record.score, 50)

    def test_mixed_flags_cap(self):
        """2 HIGH + 3 MEDIUM = 50 + 30 = 80 raw → capped at 50."""
        for _ in range(2):
            _make_red_flag(self.tender, "HIGH")
        for _ in range(3):
            _make_red_flag(self.tender, "MEDIUM")
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertEqual(score_record.red_flag_contribution, 50)

    def test_ml_scores_only_no_flags(self):
        """ml_anomaly=1.0, ml_collusion=1.0 → 30 + 20 = 50."""
        from scoring.models import FraudRiskScore
        # Seed a prior ML score row
        FraudRiskScore.objects.create(
            tender=self.tender,
            score=0,
            ml_anomaly_score=Decimal("1.0000"),
            ml_collusion_score=Decimal("1.0000"),
            model_version="v1",
        )
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertEqual(score_record.score, 50)

    def test_full_score_clamped_to_100(self):
        """3 HIGH flags (capped 50) + ml_anomaly=1.0 (30) + ml_collusion=1.0 (20) = 100."""
        from scoring.models import FraudRiskScore
        for _ in range(3):
            _make_red_flag(self.tender, "HIGH")
        FraudRiskScore.objects.create(
            tender=self.tender,
            score=0,
            ml_anomaly_score=Decimal("1.0000"),
            ml_collusion_score=Decimal("1.0000"),
            model_version="v1",
        )
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertEqual(score_record.score, 100)

    def test_score_never_below_zero(self):
        """Score must be clamped to 0 even with negative ML contributions (shouldn't happen, but guard)."""
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertGreaterEqual(score_record.score, 0)

    def test_score_never_above_100(self):
        """Score must never exceed 100."""
        from scoring.models import FraudRiskScore
        for _ in range(10):
            _make_red_flag(self.tender, "HIGH")
        FraudRiskScore.objects.create(
            tender=self.tender,
            score=0,
            ml_anomaly_score=Decimal("1.0000"),
            ml_collusion_score=Decimal("1.0000"),
            model_version="v1",
        )
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertLessEqual(score_record.score, 100)


# ------------------------------------------------------------------ #
# Custom weight tests                                                  #
# ------------------------------------------------------------------ #

class CustomWeightTest(TestCase):
    """Tests for custom weight overrides."""

    def setUp(self):
        self.tender = _make_tender(self)
        self.scorer = RiskScorer()

    def test_custom_high_weight(self):
        _make_red_flag(self.tender, "HIGH")
        weights = ScoringWeights(high_weight=10, medium_weight=5, red_flag_cap=100,
                                  ml_anomaly_weight=0, ml_collusion_weight=0)
        score_record = self.scorer.compute_score(self.tender.pk, weights=weights)
        self.assertEqual(score_record.score, 10)

    def test_custom_medium_weight(self):
        _make_red_flag(self.tender, "MEDIUM")
        weights = ScoringWeights(high_weight=0, medium_weight=15, red_flag_cap=100,
                                  ml_anomaly_weight=0, ml_collusion_weight=0)
        score_record = self.scorer.compute_score(self.tender.pk, weights=weights)
        self.assertEqual(score_record.score, 15)

    def test_custom_ml_weights(self):
        from scoring.models import FraudRiskScore
        FraudRiskScore.objects.create(
            tender=self.tender,
            score=0,
            ml_anomaly_score=Decimal("1.0000"),
            ml_collusion_score=Decimal("1.0000"),
            model_version="v1",
        )
        weights = ScoringWeights(high_weight=0, medium_weight=0, red_flag_cap=50,
                                  ml_anomaly_weight=40, ml_collusion_weight=40)
        score_record = self.scorer.compute_score(self.tender.pk, weights=weights)
        # 40 + 40 = 80
        self.assertEqual(score_record.score, 80)

    def test_weight_config_stored_in_record(self):
        weights = ScoringWeights(high_weight=20, medium_weight=8, red_flag_cap=60,
                                  ml_anomaly_weight=25, ml_collusion_weight=15)
        score_record = self.scorer.compute_score(self.tender.pk, weights=weights)
        self.assertEqual(score_record.weight_config["high_weight"], 20)
        self.assertEqual(score_record.weight_config["medium_weight"], 8)

    def test_db_weight_config_overrides_caller(self):
        """ScoringWeightConfig in DB takes priority over caller-supplied weights."""
        from scoring.models import ScoringWeightConfig
        from authentication.models import User
        admin = User.objects.create_user(username="admin_w", email="admin_w@test.com", password="pass", role="ADMIN")
        ScoringWeightConfig.objects.create(
            weights={
                "high_weight": 5,
                "medium_weight": 2,
                "red_flag_cap": 100,
                "ml_anomaly_weight": 0,
                "ml_collusion_weight": 0,
            },
            is_active=True,
            created_by=admin,
        )
        _make_red_flag(self.tender, "HIGH")
        # Caller passes different weights — DB config should win
        caller_weights = ScoringWeights(high_weight=99)
        score_record = self.scorer.compute_score(self.tender.pk, weights=caller_weights)
        self.assertEqual(score_record.score, 5)


# ------------------------------------------------------------------ #
# Persistence and AuditLog tests                                       #
# ------------------------------------------------------------------ #

class ScorePersistenceTest(TestCase):
    """Tests for score persistence and audit logging."""

    def setUp(self):
        self.tender = _make_tender(self)
        self.scorer = RiskScorer()

    def test_new_row_created_each_call(self):
        from scoring.models import FraudRiskScore
        self.scorer.compute_score(self.tender.pk)
        self.scorer.compute_score(self.tender.pk)
        count = FraudRiskScore.objects.filter(tender=self.tender).count()
        self.assertEqual(count, 2)

    def test_computed_at_is_set(self):
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertIsNotNone(score_record.computed_at)

    def test_audit_log_entry_created(self):
        from audit.models import AuditLog, EventType
        self.scorer.compute_score(self.tender.pk)
        log = AuditLog.objects.filter(
            event_type=EventType.SCORE_COMPUTED,
            affected_entity_type="Tender",
            affected_entity_id=str(self.tender.pk),
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.data_snapshot["tender_id"], self.tender.pk)

    def test_audit_log_contains_score(self):
        from audit.models import AuditLog, EventType
        _make_red_flag(self.tender, "HIGH")
        self.scorer.compute_score(self.tender.pk)
        log = AuditLog.objects.filter(
            event_type=EventType.SCORE_COMPUTED,
            affected_entity_type="Tender",
            affected_entity_id=str(self.tender.pk),
        ).first()
        self.assertEqual(log.data_snapshot["score"], 25)


# ------------------------------------------------------------------ #
# get_score tests                                                      #
# ------------------------------------------------------------------ #

class GetScoreTest(TestCase):
    """Tests for RiskScorer.get_score()."""

    def setUp(self):
        self.tender = _make_tender(self)
        self.scorer = RiskScorer()

    def test_get_score_returns_none_when_no_scores(self):
        result = self.scorer.get_score(self.tender.pk)
        self.assertIsNone(result)

    def test_get_score_returns_latest(self):
        from scoring.models import FraudRiskScore
        FraudRiskScore.objects.create(tender=self.tender, score=10, computed_at=timezone.now() - timezone.timedelta(hours=2))
        FraudRiskScore.objects.create(tender=self.tender, score=55, computed_at=timezone.now())
        result = self.scorer.get_score(self.tender.pk)
        self.assertEqual(result.score, 55)

    def test_get_score_after_compute(self):
        _make_red_flag(self.tender, "HIGH")
        self.scorer.compute_score(self.tender.pk)
        result = self.scorer.get_score(self.tender.pk)
        self.assertIsNotNone(result)
        self.assertEqual(result.score, 25)


# ------------------------------------------------------------------ #
# ML-null fallback tests                                               #
# ------------------------------------------------------------------ #

class MLNullFallbackTest(TestCase):
    """When no ML scores exist, scoring uses red flags only."""

    def setUp(self):
        self.tender = _make_tender(self)
        self.scorer = RiskScorer()

    def test_ml_null_stored_when_no_ml_available(self):
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertIsNone(score_record.ml_anomaly_score)
        self.assertIsNone(score_record.ml_collusion_score)

    def test_score_uses_flags_only_when_ml_null(self):
        _make_red_flag(self.tender, "MEDIUM")
        score_record = self.scorer.compute_score(self.tender.pk)
        self.assertEqual(score_record.score, 10)
