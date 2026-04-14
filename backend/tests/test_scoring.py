# Feature: tender-shield, Property 10: Fraud Risk Score Formula and Bounds
#
# For any combination of active RedFlag severities and ML scores, the computed
# score equals the weighted aggregate formula clamped to [0, 100]; custom
# weight overrides replace defaults when configured.
# Validates: Requirements 5.1, 5.2, 5.6

from dataclasses import dataclass
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

from detection.models import FlagType, RedFlag, Severity
from scoring.models import FraudRiskScore, ScoringWeightConfig
from scoring.scorer import (
    DEFAULT_HIGH_WEIGHT,
    DEFAULT_MEDIUM_WEIGHT,
    DEFAULT_ML_ANOMALY_WEIGHT,
    DEFAULT_ML_COLLUSION_WEIGHT,
    DEFAULT_RED_FLAG_CAP,
    RiskScorer,
    ScoringWeights,
)
from tenders.models import Tender

# ---------------------------------------------------------------------------
# ScoringInputs dataclass (strategy target)
# ---------------------------------------------------------------------------

@dataclass
class ScoringInputs:
    high_flags: int
    medium_flags: int
    ml_anomaly: float
    ml_collusion: float


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_tender_counter = 0


def _make_tender():
    global _tender_counter
    _tender_counter += 1
    return Tender.objects.create(
        tender_id=f"PBT-SCORE-{_tender_counter}",
        title="PBT Scoring Tender",
        category="IT",
        estimated_value=Decimal("100000.00"),
        currency="INR",
        submission_deadline=timezone.now() + timezone.timedelta(days=10),
        buyer_id="PBT-BUYER",
        buyer_name="PBT Buyer",
    )


def _make_red_flag(tender, severity):
    return RedFlag.objects.create(
        tender=tender,
        flag_type=FlagType.SINGLE_BIDDER,
        severity=severity,
        rule_version="1",
        trigger_data={},
        is_active=True,
    )


def _seed_ml_scores(tender, ml_anomaly: float, ml_collusion: float):
    """Seed a prior FraudRiskScore row so RiskScorer._get_latest_ml_scores picks it up."""
    FraudRiskScore.objects.create(
        tender=tender,
        score=0,
        ml_anomaly_score=Decimal(str(round(ml_anomaly, 4))),
        ml_collusion_score=Decimal(str(round(ml_collusion, 4))),
        model_version="v-pbt",
    )


def _expected_score(inputs: ScoringInputs, weights: ScoringWeights) -> int:
    """Reference implementation of the scoring formula."""
    raw_flags = (
        inputs.high_flags * weights.high_weight
        + inputs.medium_flags * weights.medium_weight
    )
    flag_contribution = min(raw_flags, weights.red_flag_cap)
    ml_contribution = (
        inputs.ml_anomaly * weights.ml_anomaly_weight
        + inputs.ml_collusion * weights.ml_collusion_weight
    )
    raw = flag_contribution + ml_contribution
    return max(0, min(100, int(round(raw))))


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

_scoring_inputs_st = st.builds(
    ScoringInputs,
    high_flags=st.integers(0, 10),
    medium_flags=st.integers(0, 10),
    ml_anomaly=st.floats(0, 1, allow_nan=False, allow_infinity=False),
    ml_collusion=st.floats(0, 1, allow_nan=False, allow_infinity=False),
)


# ===========================================================================
# Property 10a — Formula correctness with default weights
# ===========================================================================

class ScoringFormulaPropertyTest(TestCase):
    """
    Property 10: For any combination of active RedFlag severities and ML scores,
    the computed score equals the weighted aggregate formula clamped to [0, 100].
    Validates: Requirements 5.1, 5.2
    """

    @given(_scoring_inputs_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_score_matches_formula_with_default_weights(self, inputs: ScoringInputs):
        # Feature: tender-shield, Property 10: Fraud Risk Score Formula and Bounds
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()

            for _ in range(inputs.high_flags):
                _make_red_flag(tender, Severity.HIGH)
            for _ in range(inputs.medium_flags):
                _make_red_flag(tender, Severity.MEDIUM)

            _seed_ml_scores(tender, inputs.ml_anomaly, inputs.ml_collusion)

            scorer = RiskScorer()
            score_record = scorer.compute_score(tender.pk)

        default_weights = ScoringWeights()
        expected = _expected_score(inputs, default_weights)

        assert score_record.score == expected, (
            f"Score mismatch for inputs={inputs}: "
            f"got {score_record.score}, expected {expected}"
        )

    @given(_scoring_inputs_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_score_always_in_bounds(self, inputs: ScoringInputs):
        # Feature: tender-shield, Property 10: Fraud Risk Score Formula and Bounds
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()

            for _ in range(inputs.high_flags):
                _make_red_flag(tender, Severity.HIGH)
            for _ in range(inputs.medium_flags):
                _make_red_flag(tender, Severity.MEDIUM)

            _seed_ml_scores(tender, inputs.ml_anomaly, inputs.ml_collusion)

            scorer = RiskScorer()
            score_record = scorer.compute_score(tender.pk)

        assert 0 <= score_record.score <= 100, (
            f"Score {score_record.score} is outside [0, 100] for inputs={inputs}"
        )

    @given(_scoring_inputs_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_red_flag_contribution_capped_at_50(self, inputs: ScoringInputs):
        # Feature: tender-shield, Property 10: Fraud Risk Score Formula and Bounds
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()

            for _ in range(inputs.high_flags):
                _make_red_flag(tender, Severity.HIGH)
            for _ in range(inputs.medium_flags):
                _make_red_flag(tender, Severity.MEDIUM)

            scorer = RiskScorer()
            score_record = scorer.compute_score(tender.pk)

        assert score_record.red_flag_contribution <= DEFAULT_RED_FLAG_CAP, (
            f"red_flag_contribution {score_record.red_flag_contribution} "
            f"exceeds cap {DEFAULT_RED_FLAG_CAP}"
        )


# ===========================================================================
# Property 10b — Custom weight overrides replace defaults
# ===========================================================================

_custom_weights_st = st.builds(
    ScoringWeights,
    high_weight=st.integers(0, 50),
    medium_weight=st.integers(0, 30),
    red_flag_cap=st.integers(0, 100),
    ml_anomaly_weight=st.integers(0, 50),
    ml_collusion_weight=st.integers(0, 50),
)


class CustomWeightPropertyTest(TestCase):
    """
    Property 10: Custom weight overrides replace defaults when configured
    by an Administrator.
    Validates: Requirement 5.6
    """

    @given(_scoring_inputs_st, _custom_weights_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_custom_weights_replace_defaults(self, inputs: ScoringInputs, weights: ScoringWeights):
        # Feature: tender-shield, Property 10: Fraud Risk Score Formula and Bounds (custom weights)
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()

            for _ in range(inputs.high_flags):
                _make_red_flag(tender, Severity.HIGH)
            for _ in range(inputs.medium_flags):
                _make_red_flag(tender, Severity.MEDIUM)

            _seed_ml_scores(tender, inputs.ml_anomaly, inputs.ml_collusion)

            scorer = RiskScorer()
            score_record = scorer.compute_score(tender.pk, weights=weights)

        expected = _expected_score(inputs, weights)

        assert score_record.score == expected, (
            f"Score mismatch with custom weights={weights}, inputs={inputs}: "
            f"got {score_record.score}, expected {expected}"
        )

    @given(_scoring_inputs_st, _custom_weights_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_custom_weights_stored_in_record(self, inputs: ScoringInputs, weights: ScoringWeights):
        # Feature: tender-shield, Property 10: Fraud Risk Score Formula and Bounds (weight persistence)
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            scorer = RiskScorer()
            score_record = scorer.compute_score(tender.pk, weights=weights)

        assert score_record.weight_config["high_weight"] == weights.high_weight
        assert score_record.weight_config["medium_weight"] == weights.medium_weight
        assert score_record.weight_config["ml_anomaly_weight"] == weights.ml_anomaly_weight
        assert score_record.weight_config["ml_collusion_weight"] == weights.ml_collusion_weight

    @given(_scoring_inputs_st, _custom_weights_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_db_weight_config_overrides_caller_weights(self, inputs: ScoringInputs, weights: ScoringWeights):
        # Feature: tender-shield, Property 10: Fraud Risk Score Formula and Bounds (DB config priority)
        from authentication.models import User

        db_weights = ScoringWeights(
            high_weight=3,
            medium_weight=2,
            red_flag_cap=100,
            ml_anomaly_weight=5,
            ml_collusion_weight=5,
        )

        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()

            admin = User.objects.create_user(
                username=f"admin-pbt-{tender.pk}",
                email=f"admin-pbt-{tender.pk}@test.com",
                password="pass",
                role="ADMIN",
            )
            ScoringWeightConfig.objects.create(
                weights=db_weights.to_dict(),
                is_active=True,
                created_by=admin,
            )

            for _ in range(inputs.high_flags):
                _make_red_flag(tender, Severity.HIGH)
            for _ in range(inputs.medium_flags):
                _make_red_flag(tender, Severity.MEDIUM)

            _seed_ml_scores(tender, inputs.ml_anomaly, inputs.ml_collusion)

            scorer = RiskScorer()
            # Pass caller weights — DB config must win
            score_record = scorer.compute_score(tender.pk, weights=weights)

        expected = _expected_score(inputs, db_weights)

        assert score_record.score == expected, (
            f"DB weight config should override caller weights. "
            f"inputs={inputs}, db_weights={db_weights}: "
            f"got {score_record.score}, expected {expected}"
        )
