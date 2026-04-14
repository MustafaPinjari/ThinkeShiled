# Feature: tender-shield, Property 8: Bid Screens Computed for Sufficient Bids
# Feature: tender-shield, Property 9: ML Model Outputs Bounded in [0, 1]
#
# Property 8 — For any tender with >= 3 bids, all three bid screens
# (cv_bids, bid_spread_ratio, norm_winning_distance) are non-null; for any
# tender with < 3 bids, compute_bid_screens returns None (ML scores are null).
# Validates: Requirements 4.1, 4.5
#
# Property 9 — For any valid 9-feature vector, Isolation Forest anomaly score
# and Random Forest collusion probability are both in [0.0, 1.0].
# Validates: Requirements 4.2, 4.3

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, timedelta
from types import ModuleType
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, settings, assume, HealthCheck
from hypothesis import strategies as st

# ---------------------------------------------------------------------------
# sys.path bootstrap — ensure backend/ and workspace root are importable
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT_DIR = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
for _p in (_BACKEND_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Imports under test (pure Python — no Django ORM required)
# ---------------------------------------------------------------------------

from ml_worker.services.feature_engineering import compute_bid_screens  # noqa: E402
from ml_worker.train import (  # noqa: E402
    FEATURE_COLUMNS,
    train_isolation_forest,
    train_random_forest,
    predict_anomaly_score,
    predict_collusion_score,
)

# ---------------------------------------------------------------------------
# Shared strategies
# ---------------------------------------------------------------------------

# Positive floats suitable for bid amounts (avoid zero to prevent division errors)
_bid_amount_st = st.floats(min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)

# A single bid dict (no winner flag — we set one explicitly in helpers)
_bid_st = st.fixed_dictionaries({
    "bid_amount": _bid_amount_st,
    "is_winner": st.just(False),
    "submission_timestamp": st.just(datetime(2024, 1, 1, tzinfo=timezone.utc)),
    "bidder_id": st.just("bidder-1"),
})

# Tender dict with sensible defaults
_tender_st = st.fixed_dictionaries({
    "estimated_value": _bid_amount_st,
    "submission_deadline": st.just(datetime(2024, 3, 1, tzinfo=timezone.utc)),
    "publication_date": st.just(datetime(2024, 2, 1, tzinfo=timezone.utc)),
    "category": st.just("IT"),
    "id": st.just(1),
})


def _mark_first_winner(bids: list[dict]) -> list[dict]:
    """Return a copy of bids with the first bid marked as winner."""
    if not bids:
        return bids
    result = [dict(b) for b in bids]
    result[0]["is_winner"] = True
    return result


# ===========================================================================
# Property 8 — Bid Screens Computed for Sufficient Bids
# ===========================================================================

class TestProperty8BidScreens:
    """
    Property 8: compute_bid_screens returns None when bid count < 3, and
    returns a dict with all required keys (including cv_bids, bid_spread_ratio,
    norm_winning_distance) when bid count >= 3.
    """

    # -----------------------------------------------------------------------
    # 8a: fewer than 3 bids → None (ML scores must be null per Req 4.5)
    # -----------------------------------------------------------------------

    @given(
        bids=st.lists(_bid_st, min_size=0, max_size=2),
        tender=_tender_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_fewer_than_3_bids_returns_none(self, bids, tender):
        """For any bid list with < 3 entries, compute_bid_screens returns None."""
        result = compute_bid_screens(bids, tender)
        assert result is None, (
            f"Expected None for {len(bids)} bids, got {result}"
        )

    @given(tender=_tender_st)
    @settings(max_examples=50)
    def test_zero_bids_returns_none(self, tender):
        """Edge case: empty bid list returns None."""
        assert compute_bid_screens([], tender) is None

    @given(tender=_tender_st, bid=_bid_st)
    @settings(max_examples=50)
    def test_one_bid_returns_none(self, tender, bid):
        """Edge case: exactly 1 bid returns None."""
        assert compute_bid_screens([bid], tender) is None

    @given(tender=_tender_st, bid1=_bid_st, bid2=_bid_st)
    @settings(max_examples=50)
    def test_two_bids_returns_none(self, tender, bid1, bid2):
        """Edge case: exactly 2 bids returns None."""
        assert compute_bid_screens([bid1, bid2], tender) is None

    # -----------------------------------------------------------------------
    # 8b: 3 or more bids → all required bid screens are non-null
    # -----------------------------------------------------------------------

    @given(
        bids=st.lists(_bid_st, min_size=3, max_size=20),
        tender=_tender_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_3_or_more_bids_returns_dict(self, bids, tender):
        """For any bid list with >= 3 entries, compute_bid_screens returns a dict."""
        bids = _mark_first_winner(bids)
        result = compute_bid_screens(bids, tender)
        assert result is not None, (
            f"Expected dict for {len(bids)} bids, got None"
        )
        assert isinstance(result, dict)

    @given(
        bids=st.lists(_bid_st, min_size=3, max_size=20),
        tender=_tender_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_cv_bids_is_non_null(self, bids, tender):
        """cv_bids must be non-null for >= 3 bids (Requirement 4.1)."""
        bids = _mark_first_winner(bids)
        result = compute_bid_screens(bids, tender)
        assert result is not None
        assert result["cv_bids"] is not None
        assert isinstance(result["cv_bids"], float)

    @given(
        bids=st.lists(_bid_st, min_size=3, max_size=20),
        tender=_tender_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_bid_spread_ratio_is_non_null(self, bids, tender):
        """bid_spread_ratio must be non-null for >= 3 bids (Requirement 4.1)."""
        bids = _mark_first_winner(bids)
        result = compute_bid_screens(bids, tender)
        assert result is not None
        assert result["bid_spread_ratio"] is not None
        assert isinstance(result["bid_spread_ratio"], float)

    @given(
        bids=st.lists(_bid_st, min_size=3, max_size=20),
        tender=_tender_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_norm_winning_distance_is_non_null(self, bids, tender):
        """norm_winning_distance must be non-null for >= 3 bids (Requirement 4.1)."""
        bids = _mark_first_winner(bids)
        result = compute_bid_screens(bids, tender)
        assert result is not None
        assert result["norm_winning_distance"] is not None
        assert isinstance(result["norm_winning_distance"], float)

    @given(
        bids=st.lists(_bid_st, min_size=3, max_size=20),
        tender=_tender_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_all_9_feature_keys_present(self, bids, tender):
        """All 9 FEATURE_COLUMNS must be present in the result dict."""
        bids = _mark_first_winner(bids)
        result = compute_bid_screens(bids, tender)
        assert result is not None
        assert set(result.keys()) == set(FEATURE_COLUMNS), (
            f"Missing keys: {set(FEATURE_COLUMNS) - set(result.keys())}"
        )

    # -----------------------------------------------------------------------
    # 8c: boundary — exactly 3 bids is the minimum for non-null screens
    # -----------------------------------------------------------------------

    @given(
        bid1=_bid_st,
        bid2=_bid_st,
        bid3=_bid_st,
        tender=_tender_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_exactly_3_bids_returns_non_null_screens(self, bid1, bid2, bid3, tender):
        """Boundary: exactly 3 bids must produce non-null bid screens."""
        bids = _mark_first_winner([bid1, bid2, bid3])
        result = compute_bid_screens(bids, tender)
        assert result is not None
        assert result["cv_bids"] is not None
        assert result["bid_spread_ratio"] is not None
        assert result["norm_winning_distance"] is not None

    # -----------------------------------------------------------------------
    # 8d: bidder_count in result matches actual bid list length
    # -----------------------------------------------------------------------

    @given(
        bids=st.lists(_bid_st, min_size=3, max_size=20),
        tender=_tender_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_bidder_count_matches_bid_list_length(self, bids, tender):
        """bidder_count in result must equal len(bids)."""
        bids = _mark_first_winner(bids)
        result = compute_bid_screens(bids, tender)
        assert result is not None
        assert result["bidder_count"] == len(bids)

    # -----------------------------------------------------------------------
    # 8e: single_bidder_flag is 0 for >= 3 bids (since len >= 3 > 1)
    # -----------------------------------------------------------------------

    @given(
        bids=st.lists(_bid_st, min_size=3, max_size=20),
        tender=_tender_st,
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_single_bidder_flag_is_zero_for_3_or_more_bids(self, bids, tender):
        """single_bidder_flag must be 0 when there are >= 3 bids."""
        bids = _mark_first_winner(bids)
        result = compute_bid_screens(bids, tender)
        assert result is not None
        assert result["single_bidder_flag"] == 0


# ===========================================================================
# Property 9 — ML Model Outputs Bounded in [0, 1]
# ===========================================================================

# Strategy: 9-feature vector with floats in [0, 1e6]
_feature_vector_st = st.lists(
    st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    min_size=9,
    max_size=9,
)


def _vector_to_dict(values: list[float]) -> dict:
    """Map a 9-element list to a feature dict keyed by FEATURE_COLUMNS."""
    return dict(zip(FEATURE_COLUMNS, values))


def _make_training_df(n_rows: int = 30, seed: int = 42) -> pd.DataFrame:
    """Generate a minimal training DataFrame with all 9 feature columns."""
    rng = np.random.default_rng(seed)
    data = {col: rng.uniform(0.0, 10.0, size=n_rows) for col in FEATURE_COLUMNS}
    return pd.DataFrame(data)


def _make_labels(n_rows: int = 30, seed: int = 42) -> pd.Series:
    """Generate binary labels (roughly balanced)."""
    rng = np.random.default_rng(seed)
    return pd.Series((rng.random(n_rows) > 0.5).astype(int), name="label")


class TestProperty9MLOutputsBounded:
    """
    Property 9: For any valid 9-feature vector, both ML model outputs are
    in [0.0, 1.0].
    """

    # Shared trained models (created once per class to keep tests fast)
    @pytest.fixture(scope="class")
    def trained_if(self, tmp_path_factory):
        """Trained IsolationForest fixture."""
        tmp = tmp_path_factory.mktemp("models_if")
        os.environ["ML_MODEL_PATH"] = str(tmp)
        df = _make_training_df()
        return train_isolation_forest(df, contamination=0.05, random_state=0)

    @pytest.fixture(scope="class")
    def trained_rf(self, tmp_path_factory):
        """Trained RandomForest fixture."""
        tmp = tmp_path_factory.mktemp("models_rf")
        os.environ["ML_MODEL_PATH"] = str(tmp)
        df = _make_training_df()
        labels = _make_labels()
        return train_random_forest(df, labels, random_state=0)

    # -----------------------------------------------------------------------
    # 9a: Isolation Forest anomaly score in [0, 1]
    # -----------------------------------------------------------------------

    @given(feature_values=_feature_vector_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_isolation_forest_score_in_unit_interval(self, feature_values, trained_if):
        """Isolation Forest anomaly score must be in [0.0, 1.0] (Requirement 4.2)."""
        fv = _vector_to_dict(feature_values)
        score = predict_anomaly_score(trained_if.model, trained_if.scaler, fv)
        assert isinstance(score, float), f"Expected float, got {type(score)}"
        assert 0.0 <= score <= 1.0, (
            f"Anomaly score {score} is outside [0, 1] for feature vector {fv}"
        )

    @given(feature_values=_feature_vector_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_isolation_forest_score_not_nan(self, feature_values, trained_if):
        """Isolation Forest score must never be NaN."""
        fv = _vector_to_dict(feature_values)
        score = predict_anomaly_score(trained_if.model, trained_if.scaler, fv)
        assert not np.isnan(score), f"Anomaly score is NaN for feature vector {fv}"

    @given(feature_values=_feature_vector_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_isolation_forest_score_lower_bound(self, feature_values, trained_if):
        """Isolation Forest score must be >= 0.0."""
        fv = _vector_to_dict(feature_values)
        score = predict_anomaly_score(trained_if.model, trained_if.scaler, fv)
        assert score >= 0.0, f"Anomaly score {score} < 0.0"

    @given(feature_values=_feature_vector_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_isolation_forest_score_upper_bound(self, feature_values, trained_if):
        """Isolation Forest score must be <= 1.0."""
        fv = _vector_to_dict(feature_values)
        score = predict_anomaly_score(trained_if.model, trained_if.scaler, fv)
        assert score <= 1.0, f"Anomaly score {score} > 1.0"

    # -----------------------------------------------------------------------
    # 9b: Random Forest collusion probability in [0, 1]
    # -----------------------------------------------------------------------

    @given(feature_values=_feature_vector_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_random_forest_score_in_unit_interval(self, feature_values, trained_rf):
        """Random Forest collusion probability must be in [0.0, 1.0] (Requirement 4.3)."""
        fv = _vector_to_dict(feature_values)
        score = predict_collusion_score(trained_rf.model, fv)
        assert isinstance(score, float), f"Expected float, got {type(score)}"
        assert 0.0 <= score <= 1.0, (
            f"Collusion score {score} is outside [0, 1] for feature vector {fv}"
        )

    @given(feature_values=_feature_vector_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_random_forest_score_not_nan(self, feature_values, trained_rf):
        """Random Forest collusion score must never be NaN."""
        fv = _vector_to_dict(feature_values)
        score = predict_collusion_score(trained_rf.model, fv)
        assert not np.isnan(score), f"Collusion score is NaN for feature vector {fv}"

    @given(feature_values=_feature_vector_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_random_forest_score_lower_bound(self, feature_values, trained_rf):
        """Random Forest collusion score must be >= 0.0."""
        fv = _vector_to_dict(feature_values)
        score = predict_collusion_score(trained_rf.model, fv)
        assert score >= 0.0, f"Collusion score {score} < 0.0"

    @given(feature_values=_feature_vector_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_random_forest_score_upper_bound(self, feature_values, trained_rf):
        """Random Forest collusion score must be <= 1.0."""
        fv = _vector_to_dict(feature_values)
        score = predict_collusion_score(trained_rf.model, fv)
        assert score <= 1.0, f"Collusion score {score} > 1.0"

    # -----------------------------------------------------------------------
    # 9c: Both models bounded simultaneously (combined property)
    # -----------------------------------------------------------------------

    @given(feature_values=_feature_vector_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow])
    def test_both_scores_bounded_simultaneously(self, feature_values, trained_if, trained_rf):
        """Both IF anomaly score and RF collusion score are in [0, 1] for the same input."""
        fv = _vector_to_dict(feature_values)
        anomaly = predict_anomaly_score(trained_if.model, trained_if.scaler, fv)
        collusion = predict_collusion_score(trained_rf.model, fv)
        assert 0.0 <= anomaly <= 1.0, f"Anomaly score {anomaly} out of bounds"
        assert 0.0 <= collusion <= 1.0, f"Collusion score {collusion} out of bounds"

    # -----------------------------------------------------------------------
    # 9d: Extreme feature values (large magnitudes) still produce bounded output
    # -----------------------------------------------------------------------

    def test_extreme_large_feature_values_if_bounded(self, trained_if):
        """Extreme large feature values must not push IF score outside [0, 1]."""
        fv = _vector_to_dict([1e6] * 9)
        score = predict_anomaly_score(trained_if.model, trained_if.scaler, fv)
        assert 0.0 <= score <= 1.0

    def test_extreme_zero_feature_values_if_bounded(self, trained_if):
        """All-zero feature vector must produce IF score in [0, 1]."""
        fv = _vector_to_dict([0.0] * 9)
        score = predict_anomaly_score(trained_if.model, trained_if.scaler, fv)
        assert 0.0 <= score <= 1.0

    def test_extreme_large_feature_values_rf_bounded(self, trained_rf):
        """Extreme large feature values must not push RF score outside [0, 1]."""
        fv = _vector_to_dict([1e6] * 9)
        score = predict_collusion_score(trained_rf.model, fv)
        assert 0.0 <= score <= 1.0

    def test_extreme_zero_feature_values_rf_bounded(self, trained_rf):
        """All-zero feature vector must produce RF score in [0, 1]."""
        fv = _vector_to_dict([0.0] * 9)
        score = predict_collusion_score(trained_rf.model, fv)
        assert 0.0 <= score <= 1.0
