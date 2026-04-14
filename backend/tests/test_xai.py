# Feature: tender-shield, Property 11: SHAP Explanation Completeness
# Feature: tender-shield, Property 12: Explanation Version Stamps
#
# Property 11: For any tender with ML scores, the SHAP explanation contains a
# value for every feature in the feature vector, top-5 factors are present and
# sorted by absolute SHAP magnitude, and all active RedFlags appear in the
# explanation output.
# Validates: Requirements 6.1, 6.2, 6.4
#
# Property 12: For any generated explanation, model_version and
# rule_engine_version are non-null and match the currently active versions.
# Validates: Requirements 6.5

from __future__ import annotations

import hashlib
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

from detection.models import FlagType, RedFlag, RuleDefinition, Severity
from tenders.models import Tender
from xai.explainer import XAIExplainer
from xai.models import MLModelType, MLModelVersion, SHAPExplanation

# ---------------------------------------------------------------------------
# Constants
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

_tender_counter = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_tender(**kwargs) -> Tender:
    global _tender_counter
    _tender_counter += 1
    defaults = {
        "tender_id": f"XAI-PBT-{_tender_counter}",
        "title": "XAI PBT Tender",
        "category": "IT",
        "estimated_value": Decimal("100000.00"),
        "currency": "INR",
        "submission_deadline": timezone.now() + timedelta(days=30),
        "buyer_id": "XAI-BUYER",
        "buyer_name": "XAI Buyer",
    }
    defaults.update(kwargs)
    return Tender.objects.create(**defaults)


def _make_shap_values(seed: int = 0) -> dict:
    """Return deterministic SHAP values for all 9 features."""
    result = {}
    for col in FEATURE_COLUMNS:
        h = int(hashlib.md5(f"{seed}-{col}".encode()).hexdigest(), 16)
        result[col] = ((h % 2000) - 1000) / 1000.0  # range [-1, 1]
    return result


def _make_top_factors(shap_values: dict, n: int = 5) -> list:
    """Build top_factors list sorted by |SHAP| descending."""
    sorted_features = sorted(
        FEATURE_COLUMNS, key=lambda f: abs(shap_values[f]), reverse=True
    )
    return [
        {
            "feature": f,
            "shap_value": shap_values[f],
            "feature_value": 0.5,
            "explanation": f"Explanation for {f}",
        }
        for f in sorted_features[:n]
    ]


def _make_shap_explanation(
    tender: Tender,
    model_version: str = "RF:v1",
    rule_engine_version: str = "1.0",
    shap_failed: bool = False,
    seed: int = 0,
) -> SHAPExplanation:
    shap_values = {} if shap_failed else _make_shap_values(seed)
    top_factors = [] if shap_failed else _make_top_factors(shap_values)
    return SHAPExplanation.objects.create(
        tender=tender,
        model_version=model_version,
        rule_engine_version=rule_engine_version,
        shap_values=shap_values,
        top_factors=top_factors,
        shap_failed=shap_failed,
    )


def _make_ml_model_version(
    model_type: str = MLModelType.RANDOM_FOREST,
    version: str = "v1",
    is_active: bool = True,
) -> MLModelVersion:
    return MLModelVersion.objects.create(
        model_type=model_type,
        version=version,
        model_artifact_path=f"/fake/{model_type}-{version}.pkl",
        is_active=is_active,
    )


def _make_rule_definition(
    rule_code: str,
    description: str = "",
    severity: str = Severity.HIGH,
) -> RuleDefinition:
    obj, _ = RuleDefinition.objects.get_or_create(
        rule_code=rule_code,
        defaults={
            "description": description or f"Rule: {rule_code}",
            "severity": severity,
            "is_active": True,
            "parameters": {},
        },
    )
    return obj


def _make_red_flag(
    tender: Tender,
    flag_type: str = FlagType.SINGLE_BIDDER,
    severity: str = Severity.HIGH,
    trigger_data: dict | None = None,
) -> RedFlag:
    return RedFlag.objects.create(
        tender=tender,
        flag_type=flag_type,
        severity=severity,
        rule_version="1.0",
        trigger_data=trigger_data or {"bid_count": 1},
        is_active=True,
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Strategy for generating a seed integer to produce deterministic SHAP values
_st_seed = st.integers(min_value=0, max_value=9999)

# Strategy for generating model version strings
_st_model_version = st.one_of(
    st.just("RF:v1"),
    st.just("RF:v2"),
    st.just("IF:v1/RF:v1"),
    st.builds(
        lambda n: f"RF:v{n}",
        st.integers(min_value=1, max_value=100),
    ),
)

# Strategy for generating rule engine version strings
_st_rule_engine_version = st.one_of(
    st.just("1.0"),
    st.just("2.0"),
    st.builds(
        lambda major, minor: f"{major}.{minor}",
        st.integers(min_value=1, max_value=9),
        st.integers(min_value=0, max_value=9),
    ),
)

# Strategy for flag types to include in a tender
_st_flag_types = st.lists(
    st.sampled_from([
        FlagType.SINGLE_BIDDER,
        FlagType.PRICE_ANOMALY,
        FlagType.SHORT_DEADLINE,
        FlagType.REPEAT_WINNER,
    ]),
    min_size=0,
    max_size=4,
    unique=True,
)


# ===========================================================================
# Property 11 — SHAP Explanation Completeness
# ===========================================================================

class SHAPExplanationCompletenessPropertyTest(TestCase):
    """
    Property 11: For any tender with ML scores, the SHAP explanation contains
    a value for every feature in the feature vector, top-5 factors are present
    and sorted by absolute SHAP magnitude, and all active RedFlags appear in
    the explanation output.
    Validates: Requirements 6.1, 6.2, 6.4
    """

    @given(_st_seed)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_shap_values_has_key_for_every_feature(self, seed: int):
        # Feature: tender-shield, Property 11: SHAP Explanation Completeness
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(tender, seed=seed)

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version="RF:v1")

        assert not result["shap_failed"], "Expected successful SHAP explanation"
        shap_values = result["shap_values"]

        assert set(shap_values.keys()) == set(FEATURE_COLUMNS), (
            f"shap_values keys {set(shap_values.keys())} != expected {set(FEATURE_COLUMNS)}"
        )

    @given(_st_seed)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_shap_values_has_exactly_nine_entries(self, seed: int):
        # Feature: tender-shield, Property 11: SHAP Explanation Completeness
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(tender, seed=seed)

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version="RF:v1")

        assert not result["shap_failed"]
        assert len(result["shap_values"]) == 9, (
            f"Expected 9 SHAP values, got {len(result['shap_values'])}"
        )

    @given(_st_seed)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_top_factors_has_at_most_five_entries(self, seed: int):
        # Feature: tender-shield, Property 11: SHAP Explanation Completeness
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(tender, seed=seed)

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version="RF:v1")

        assert not result["shap_failed"]
        assert len(result["top_factors"]) <= 5, (
            f"top_factors has {len(result['top_factors'])} entries, expected ≤ 5"
        )

    @given(_st_seed)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_top_factors_has_exactly_five_entries_when_all_features_nonzero(self, seed: int):
        # Feature: tender-shield, Property 11: SHAP Explanation Completeness
        # All 9 features have non-zero SHAP values from _make_shap_values, so top-5 must be 5
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            shap_values = _make_shap_values(seed)
            # Ensure all values are non-zero (they are by construction from the hash)
            top_factors = _make_top_factors(shap_values, n=5)
            SHAPExplanation.objects.create(
                tender=tender,
                model_version="RF:v1",
                rule_engine_version="1.0",
                shap_values=shap_values,
                top_factors=top_factors,
                shap_failed=False,
            )

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version="RF:v1")

        assert not result["shap_failed"]
        assert len(result["top_factors"]) == 5, (
            f"Expected exactly 5 top_factors when all features non-zero, "
            f"got {len(result['top_factors'])}"
        )

    @given(_st_seed)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_top_factors_sorted_by_absolute_shap_magnitude_descending(self, seed: int):
        # Feature: tender-shield, Property 11: SHAP Explanation Completeness
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(tender, seed=seed)

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version="RF:v1")

        assert not result["shap_failed"]
        magnitudes = [abs(f["shap_value"]) for f in result["top_factors"]]
        assert magnitudes == sorted(magnitudes, reverse=True), (
            f"top_factors not sorted by |SHAP| descending: {magnitudes}"
        )

    @given(_st_seed, _st_flag_types)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_all_active_red_flags_appear_in_explanation(self, seed: int, flag_types: list):
        # Feature: tender-shield, Property 11: SHAP Explanation Completeness
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(tender, seed=seed)

            # Create rule definitions and active red flags
            for flag_type in flag_types:
                severity = (
                    Severity.MEDIUM
                    if flag_type == FlagType.PRICE_ANOMALY
                    else Severity.HIGH
                )
                _make_rule_definition(flag_type, severity=severity)
                _make_red_flag(tender, flag_type, severity=severity)

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version="RF:v1")

        assert not result["shap_failed"]
        returned_flag_types = {f["flag_type"] for f in result["red_flags"]}
        expected_flag_types = set(flag_types)

        assert expected_flag_types == returned_flag_types, (
            f"Expected red_flags {expected_flag_types}, got {returned_flag_types}"
        )

    @given(_st_seed)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_top_factors_each_have_required_keys(self, seed: int):
        # Feature: tender-shield, Property 11: SHAP Explanation Completeness
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(tender, seed=seed)

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version="RF:v1")

        assert not result["shap_failed"]
        for factor in result["top_factors"]:
            assert "feature" in factor, f"Missing 'feature' key in factor: {factor}"
            assert "shap_value" in factor, f"Missing 'shap_value' key in factor: {factor}"
            assert "feature_value" in factor, f"Missing 'feature_value' key in factor: {factor}"
            assert "explanation" in factor, f"Missing 'explanation' key in factor: {factor}"
            assert isinstance(factor["explanation"], str) and len(factor["explanation"]) > 0, (
                f"'explanation' must be a non-empty string, got: {factor['explanation']!r}"
            )

    @given(_st_seed)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_top_factors_feature_names_are_valid_feature_columns(self, seed: int):
        # Feature: tender-shield, Property 11: SHAP Explanation Completeness
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(tender, seed=seed)

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version="RF:v1")

        assert not result["shap_failed"]
        for factor in result["top_factors"]:
            assert factor["feature"] in FEATURE_COLUMNS, (
                f"top_factors feature '{factor['feature']}' not in FEATURE_COLUMNS"
            )

    @given(_st_seed)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_inactive_red_flags_excluded_from_explanation(self, seed: int):
        # Feature: tender-shield, Property 11: SHAP Explanation Completeness
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(tender, seed=seed)

            _make_rule_definition(FlagType.SINGLE_BIDDER)
            _make_red_flag(tender, FlagType.SINGLE_BIDDER)  # active

            # Create an inactive flag — must NOT appear in explanation
            RedFlag.objects.create(
                tender=tender,
                flag_type=FlagType.PRICE_ANOMALY,
                severity=Severity.MEDIUM,
                rule_version="1.0",
                trigger_data={"deviation_pct": 50},
                is_active=False,
            )

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version="RF:v1")

        assert not result["shap_failed"]
        returned_flag_types = {f["flag_type"] for f in result["red_flags"]}
        assert FlagType.SINGLE_BIDDER in returned_flag_types
        assert FlagType.PRICE_ANOMALY not in returned_flag_types, (
            "Inactive PRICE_ANOMALY flag must not appear in explanation"
        )


# ===========================================================================
# Property 12 — Explanation Version Stamps
# ===========================================================================

class ExplanationVersionStampsPropertyTest(TestCase):
    """
    Property 12: For any generated explanation, model_version and
    rule_engine_version are non-null and match the currently active versions.
    Validates: Requirements 6.5
    """

    @given(_st_model_version, _st_rule_engine_version)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_model_version_is_non_null(self, model_version: str, rule_engine_version: str):
        # Feature: tender-shield, Property 12: Explanation Version Stamps
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(
                tender,
                model_version=model_version,
                rule_engine_version=rule_engine_version,
            )

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version=model_version)

        assert result["model_version"] is not None, "model_version must not be None"
        assert result["model_version"] != "", "model_version must not be empty"

    @given(_st_model_version, _st_rule_engine_version)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_rule_engine_version_is_non_null(self, model_version: str, rule_engine_version: str):
        # Feature: tender-shield, Property 12: Explanation Version Stamps
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(
                tender,
                model_version=model_version,
                rule_engine_version=rule_engine_version,
            )

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version=model_version)

        assert result["rule_engine_version"] is not None, "rule_engine_version must not be None"
        assert result["rule_engine_version"] != "", "rule_engine_version must not be empty"

    @given(_st_model_version, _st_rule_engine_version)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_model_version_matches_stored_explanation(self, model_version: str, rule_engine_version: str):
        # Feature: tender-shield, Property 12: Explanation Version Stamps
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(
                tender,
                model_version=model_version,
                rule_engine_version=rule_engine_version,
            )

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version=model_version)

        assert result["model_version"] == model_version, (
            f"model_version mismatch: got {result['model_version']!r}, "
            f"expected {model_version!r}"
        )

    @given(_st_model_version, _st_rule_engine_version)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_rule_engine_version_matches_stored_explanation(self, model_version: str, rule_engine_version: str):
        # Feature: tender-shield, Property 12: Explanation Version Stamps
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(
                tender,
                model_version=model_version,
                rule_engine_version=rule_engine_version,
            )

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version=model_version)

        assert result["rule_engine_version"] == rule_engine_version, (
            f"rule_engine_version mismatch: got {result['rule_engine_version']!r}, "
            f"expected {rule_engine_version!r}"
        )

    @given(_st_model_version, _st_rule_engine_version)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_version_stamps_present_in_shap_explanation_record(
        self, model_version: str, rule_engine_version: str
    ):
        # Feature: tender-shield, Property 12: Explanation Version Stamps
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            shap_exp = _make_shap_explanation(
                tender,
                model_version=model_version,
                rule_engine_version=rule_engine_version,
            )

        # Verify the stored SHAPExplanation record itself has the stamps
        assert shap_exp.model_version is not None and shap_exp.model_version != "", (
            "SHAPExplanation.model_version must be non-null and non-empty"
        )
        assert shap_exp.rule_engine_version is not None and shap_exp.rule_engine_version != "", (
            "SHAPExplanation.rule_engine_version must be non-null and non-empty"
        )
        assert shap_exp.model_version == model_version
        assert shap_exp.rule_engine_version == rule_engine_version

    @given(_st_model_version, _st_rule_engine_version)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_version_stamps_present_in_fallback_explanation(
        self, model_version: str, rule_engine_version: str
    ):
        # Feature: tender-shield, Property 12: Explanation Version Stamps
        # Even when SHAP fails, version stamps must be present in the fallback
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            _make_shap_explanation(
                tender,
                model_version=model_version,
                rule_engine_version=rule_engine_version,
                shap_failed=True,
            )

        explainer = XAIExplainer()
        result = explainer.fallback_explain(tender.pk)

        assert result["model_version"] is not None and result["model_version"] != "", (
            "model_version must be non-null in fallback explanation"
        )
        assert result["rule_engine_version"] is not None and result["rule_engine_version"] != "", (
            "rule_engine_version must be non-null in fallback explanation"
        )
        assert result["model_version"] == model_version
        assert result["rule_engine_version"] == rule_engine_version

    @given(
        _st_model_version,
        _st_rule_engine_version,
        st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_version_stamps_match_most_recent_explanation(
        self, model_version: str, rule_engine_version: str, extra_count: int
    ):
        # Feature: tender-shield, Property 12: Explanation Version Stamps
        # When multiple SHAPExplanation records exist, the most recent one's
        # version stamps are returned.
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()

            # Create older explanations with different versions
            for i in range(extra_count):
                SHAPExplanation.objects.create(
                    tender=tender,
                    model_version=f"RF:old-v{i}",
                    rule_engine_version="0.1",
                    shap_values=_make_shap_values(i),
                    top_factors=_make_top_factors(_make_shap_values(i)),
                    shap_failed=False,
                )

            # Create the most recent explanation with the target versions
            _make_shap_explanation(
                tender,
                model_version=model_version,
                rule_engine_version=rule_engine_version,
            )

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version=model_version)

        assert result["model_version"] == model_version, (
            f"Expected most recent model_version={model_version!r}, "
            f"got {result['model_version']!r}"
        )
        assert result["rule_engine_version"] == rule_engine_version, (
            f"Expected most recent rule_engine_version={rule_engine_version!r}, "
            f"got {result['rule_engine_version']!r}"
        )

    @given(_st_model_version, _st_rule_engine_version)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_version_stamps_match_active_mlmodelversion_records(
        self, model_version: str, rule_engine_version: str
    ):
        # Feature: tender-shield, Property 12: Explanation Version Stamps
        # The version stamp in the explanation must match the MLModelVersion
        # record that was active when the explanation was generated.
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()

            # Create an active MLModelVersion record
            rf_version = _make_ml_model_version(
                model_type=MLModelType.RANDOM_FOREST,
                version=model_version,
                is_active=True,
            )

            # Create a SHAPExplanation stamped with this version
            _make_shap_explanation(
                tender,
                model_version=rf_version.version,
                rule_engine_version=rule_engine_version,
            )

        explainer = XAIExplainer()
        result = explainer.explain(tender.pk, model_version=rf_version.version)

        # The explanation's model_version must match the active MLModelVersion
        active_rf = (
            MLModelVersion.objects.filter(
                model_type=MLModelType.RANDOM_FOREST, is_active=True
            )
            .order_by("-trained_at")
            .first()
        )
        assert active_rf is not None, "Expected an active MLModelVersion record"
        assert result["model_version"] == active_rf.version, (
            f"Explanation model_version {result['model_version']!r} does not match "
            f"active MLModelVersion {active_rf.version!r}"
        )
