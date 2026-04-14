"""
Unit tests for ml_worker/train.py

Tests cover:
  - train_isolation_forest: model fitting, output range [0, 1], serialization
  - train_random_forest: model fitting, output range [0, 1], serialization
  - predict_anomaly_score / predict_collusion_score: output bounds
  - Retraining cycle: new version created, old version deactivated (mocked DB)
  - Edge cases: empty DataFrame, missing columns, NaN rows

All tests are pure Python — no database connection required.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from ml_worker.train import (
    FEATURE_COLUMNS,
    TrainedModel,
    load_isolation_forest,
    load_random_forest,
    predict_anomaly_score,
    predict_collusion_score,
    train_isolation_forest,
    train_random_forest,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_model_dir(tmp_path, monkeypatch):
    """Redirect ML_MODEL_PATH to a temp directory for each test."""
    monkeypatch.setenv("ML_MODEL_PATH", str(tmp_path))
    # Also patch the module-level constant so joblib writes there
    import ml_worker.train as train_module
    monkeypatch.setattr(train_module, "ML_MODEL_DIR", tmp_path)
    return tmp_path


def _make_feature_df(n: int = 50, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic feature DataFrame with n rows."""
    rng = np.random.default_rng(seed)
    data = {
        "cv_bids": rng.uniform(0.0, 1.0, n),
        "bid_spread_ratio": rng.uniform(1.0, 3.0, n),
        "norm_winning_distance": rng.uniform(-2.0, 2.0, n),
        "single_bidder_flag": rng.integers(0, 2, n).astype(float),
        "price_deviation_pct": rng.uniform(-0.5, 0.5, n),
        "deadline_days": rng.integers(1, 60, n).astype(float),
        "repeat_winner_rate": rng.uniform(0.0, 1.0, n),
        "bidder_count": rng.integers(1, 20, n).astype(float),
        "winner_bid_rank": rng.integers(1, 10, n).astype(float),
    }
    return pd.DataFrame(data)


def _make_labels(n: int = 50, seed: int = 42) -> pd.Series:
    """Generate binary labels (roughly 10% positive)."""
    rng = np.random.default_rng(seed)
    return pd.Series(rng.integers(0, 2, n), name="label")


def _make_feature_vector(seed: int = 0) -> dict:
    """Return a single valid feature vector dict."""
    rng = np.random.default_rng(seed)
    return {col: float(rng.uniform(0.0, 1.0)) for col in FEATURE_COLUMNS}


# ---------------------------------------------------------------------------
# train_isolation_forest
# ---------------------------------------------------------------------------

class TestTrainIsolationForest:
    def test_returns_trained_model_namedtuple(self, tmp_model_dir):
        df = _make_feature_df()
        result = train_isolation_forest(df)
        assert isinstance(result, TrainedModel)

    def test_model_type_is_isolation_forest(self, tmp_model_dir):
        result = train_isolation_forest(_make_feature_df())
        assert result.model_type == "ISOLATION_FOREST"

    def test_artifact_file_exists(self, tmp_model_dir):
        result = train_isolation_forest(_make_feature_df())
        assert Path(result.artifact_path).exists()

    def test_version_is_non_empty_string(self, tmp_model_dir):
        result = train_isolation_forest(_make_feature_df())
        assert isinstance(result.version, str) and len(result.version) > 0

    def test_scaler_is_not_none(self, tmp_model_dir):
        result = train_isolation_forest(_make_feature_df())
        assert result.scaler is not None

    def test_feature_importances_has_all_columns(self, tmp_model_dir):
        result = train_isolation_forest(_make_feature_df())
        assert set(result.feature_importances.keys()) == set(FEATURE_COLUMNS)

    def test_feature_importances_sum_to_one(self, tmp_model_dir):
        result = train_isolation_forest(_make_feature_df())
        total = sum(result.feature_importances.values())
        assert abs(total - 1.0) < 1e-6

    def test_raises_on_empty_dataframe(self, tmp_model_dir):
        with pytest.raises(ValueError, match="no valid"):
            train_isolation_forest(pd.DataFrame(columns=FEATURE_COLUMNS))

    def test_raises_on_missing_column(self, tmp_model_dir):
        df = _make_feature_df().drop(columns=["cv_bids"])
        with pytest.raises(ValueError, match="missing required columns"):
            train_isolation_forest(df)

    def test_nan_rows_are_dropped(self, tmp_model_dir):
        df = _make_feature_df(n=20)
        df.loc[0, "cv_bids"] = float("nan")
        # Should not raise — NaN row is dropped
        result = train_isolation_forest(df)
        assert result is not None

    def test_two_versions_have_different_artifact_paths(self, tmp_model_dir):
        r1 = train_isolation_forest(_make_feature_df(seed=1))
        r2 = train_isolation_forest(_make_feature_df(seed=2))
        assert r1.artifact_path != r2.artifact_path


# ---------------------------------------------------------------------------
# train_random_forest
# ---------------------------------------------------------------------------

class TestTrainRandomForest:
    def test_returns_trained_model_namedtuple(self, tmp_model_dir):
        df = _make_feature_df()
        labels = _make_labels()
        result = train_random_forest(df, labels)
        assert isinstance(result, TrainedModel)

    def test_model_type_is_random_forest(self, tmp_model_dir):
        result = train_random_forest(_make_feature_df(), _make_labels())
        assert result.model_type == "RANDOM_FOREST"

    def test_artifact_file_exists(self, tmp_model_dir):
        result = train_random_forest(_make_feature_df(), _make_labels())
        assert Path(result.artifact_path).exists()

    def test_scaler_is_none(self, tmp_model_dir):
        result = train_random_forest(_make_feature_df(), _make_labels())
        assert result.scaler is None

    def test_feature_importances_has_all_columns(self, tmp_model_dir):
        result = train_random_forest(_make_feature_df(), _make_labels())
        assert set(result.feature_importances.keys()) == set(FEATURE_COLUMNS)

    def test_feature_importances_sum_to_one(self, tmp_model_dir):
        result = train_random_forest(_make_feature_df(), _make_labels())
        total = sum(result.feature_importances.values())
        assert abs(total - 1.0) < 1e-6

    def test_raises_on_empty_dataframe(self, tmp_model_dir):
        with pytest.raises(ValueError, match="no valid rows"):
            train_random_forest(
                pd.DataFrame(columns=FEATURE_COLUMNS),
                pd.Series([], dtype=int),
            )

    def test_raises_on_missing_column(self, tmp_model_dir):
        df = _make_feature_df().drop(columns=["bidder_count"])
        with pytest.raises(ValueError, match="missing required columns"):
            train_random_forest(df, _make_labels())

    def test_nan_rows_are_dropped(self, tmp_model_dir):
        df = _make_feature_df(n=30)
        labels = _make_labels(n=30)
        df.loc[0, "cv_bids"] = float("nan")
        result = train_random_forest(df, labels)
        assert result is not None


# ---------------------------------------------------------------------------
# predict_anomaly_score — output range [0, 1]
# ---------------------------------------------------------------------------

class TestPredictAnomalyScore:
    @pytest.fixture(autouse=True)
    def _train(self, tmp_model_dir):
        result = train_isolation_forest(_make_feature_df())
        self.model = result.model
        self.scaler = result.scaler

    def test_output_in_range_for_normal_vector(self):
        fv = _make_feature_vector(seed=10)
        score = predict_anomaly_score(self.model, self.scaler, fv)
        assert 0.0 <= score <= 1.0

    def test_output_in_range_for_extreme_high_values(self):
        fv = {col: 1e9 for col in FEATURE_COLUMNS}
        score = predict_anomaly_score(self.model, self.scaler, fv)
        assert 0.0 <= score <= 1.0

    def test_output_in_range_for_zero_vector(self):
        fv = {col: 0.0 for col in FEATURE_COLUMNS}
        score = predict_anomaly_score(self.model, self.scaler, fv)
        assert 0.0 <= score <= 1.0

    def test_output_is_float(self):
        fv = _make_feature_vector()
        score = predict_anomaly_score(self.model, self.scaler, fv)
        assert isinstance(score, float)

    def test_multiple_vectors_all_in_range(self):
        rng = np.random.default_rng(99)
        for _ in range(20):
            fv = {col: float(rng.uniform(-5.0, 5.0)) for col in FEATURE_COLUMNS}
            score = predict_anomaly_score(self.model, self.scaler, fv)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for {fv}"


# ---------------------------------------------------------------------------
# predict_collusion_score — output range [0, 1]
# ---------------------------------------------------------------------------

class TestPredictCollusionScore:
    @pytest.fixture(autouse=True)
    def _train(self, tmp_model_dir):
        result = train_random_forest(_make_feature_df(), _make_labels())
        self.model = result.model

    def test_output_in_range_for_normal_vector(self):
        fv = _make_feature_vector(seed=20)
        score = predict_collusion_score(self.model, fv)
        assert 0.0 <= score <= 1.0

    def test_output_in_range_for_extreme_values(self):
        fv = {col: 1e9 for col in FEATURE_COLUMNS}
        score = predict_collusion_score(self.model, fv)
        assert 0.0 <= score <= 1.0

    def test_output_in_range_for_zero_vector(self):
        fv = {col: 0.0 for col in FEATURE_COLUMNS}
        score = predict_collusion_score(self.model, fv)
        assert 0.0 <= score <= 1.0

    def test_output_is_float(self):
        fv = _make_feature_vector()
        score = predict_collusion_score(self.model, fv)
        assert isinstance(score, float)

    def test_multiple_vectors_all_in_range(self):
        rng = np.random.default_rng(77)
        for _ in range(20):
            fv = {col: float(rng.uniform(0.0, 100.0)) for col in FEATURE_COLUMNS}
            score = predict_collusion_score(self.model, fv)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range"


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------

class TestSerializationRoundTrip:
    def test_isolation_forest_round_trip(self, tmp_model_dir):
        df = _make_feature_df()
        result = train_isolation_forest(df)
        loaded_model, loaded_scaler = load_isolation_forest(result.artifact_path)

        fv = _make_feature_vector()
        score_original = predict_anomaly_score(result.model, result.scaler, fv)
        score_loaded = predict_anomaly_score(loaded_model, loaded_scaler, fv)
        assert abs(score_original - score_loaded) < 1e-9

    def test_random_forest_round_trip(self, tmp_model_dir):
        df = _make_feature_df()
        labels = _make_labels()
        result = train_random_forest(df, labels)
        loaded_model = load_random_forest(result.artifact_path)

        fv = _make_feature_vector()
        score_original = predict_collusion_score(result.model, fv)
        score_loaded = predict_collusion_score(loaded_model, fv)
        assert abs(score_original - score_loaded) < 1e-9


# ---------------------------------------------------------------------------
# Retraining cycle — version management (mocked DB)
# ---------------------------------------------------------------------------

class TestRetrainingCycle:
    """Verify that retraining produces a new version and deactivates the old one.

    Uses mocked Django ORM objects — no database required.
    """

    def test_new_version_differs_from_old(self, tmp_model_dir):
        """Two successive training runs must produce different version strings."""
        df = _make_feature_df()
        labels = _make_labels()

        r1_if = train_isolation_forest(df, random_state=1)
        r2_if = train_isolation_forest(df, random_state=2)
        assert r1_if.version != r2_if.version

        r1_rf = train_random_forest(df, labels, random_state=1)
        r2_rf = train_random_forest(df, labels, random_state=2)
        assert r1_rf.version != r2_rf.version

    def test_new_artifact_path_differs_from_old(self, tmp_model_dir):
        """Each training run must write to a unique artifact path."""
        df = _make_feature_df()
        labels = _make_labels()

        r1 = train_isolation_forest(df)
        r2 = train_isolation_forest(df)
        assert r1.artifact_path != r2.artifact_path

        r3 = train_random_forest(df, labels)
        r4 = train_random_forest(df, labels)
        assert r3.artifact_path != r4.artifact_path

    def test_both_artifact_files_exist_after_two_runs(self, tmp_model_dir):
        """Both old and new artifacts are on disk; DB deactivation is separate."""
        df = _make_feature_df()
        r1 = train_isolation_forest(df)
        r2 = train_isolation_forest(df)
        assert Path(r1.artifact_path).exists()
        assert Path(r2.artifact_path).exists()

    def test_retrain_models_task_deactivates_old_version(self, tmp_model_dir, monkeypatch):
        """retrain_models() must deactivate old MLModelVersion records."""
        import ml_worker.tasks as tasks_module

        df = _make_feature_df()
        labels = _make_labels()

        # Pre-train models so artifacts exist
        if_result = train_isolation_forest(df)
        rf_result = train_random_forest(df, labels)

        # --- Mock Django models ---
        mock_tender = MagicMock()
        mock_tender.estimated_value = 100.0
        mock_tender.submission_deadline = pd.Timestamp("2024-02-01", tz="UTC")
        mock_tender.publication_date = pd.Timestamp("2024-01-01", tz="UTC")
        mock_tender.category = "IT"
        mock_tender.id = 1

        # Build 10 mock bids so feature engineering returns a vector
        mock_bids = []
        for i in range(10):
            b = MagicMock()
            b.bid_amount = 80 + i * 5
            b.is_winner = i == 0
            b.submission_timestamp = pd.Timestamp("2024-01-10", tz="UTC")
            b.bidder_id = f"bidder_{i}"
            b.bidder = MagicMock()
            mock_bids.append(b)

        # Mock red_flags queryset
        mock_red_flags = MagicMock()
        mock_red_flags.filter.return_value.exists.return_value = False
        mock_tender.red_flags = mock_red_flags

        # Mock bids prefetch
        mock_tender.bids.all.return_value = mock_bids

        # Mock Tender.objects.prefetch_related().all()
        mock_tender_qs = MagicMock()
        mock_tender_qs.__iter__ = MagicMock(return_value=iter([mock_tender] * 15))

        # Mock MLModelVersion queryset
        mock_mv_qs = MagicMock()
        mock_mv_qs.filter.return_value.update.return_value = 1
        mock_mv_qs.filter.return_value.order_by.return_value.first.return_value = None

        # Mock MLModelVersion.objects.create
        mock_if_mv = MagicMock()
        mock_if_mv.id = 1
        mock_rf_mv = MagicMock()
        mock_rf_mv.id = 2

        deactivated_types = []

        def mock_mv_filter(**kwargs):
            m = MagicMock()
            m.update = MagicMock(side_effect=lambda **kw: deactivated_types.append(kwargs.get("model_type")))
            return m

        mock_mlmodelversion = MagicMock()
        mock_mlmodelversion.objects.filter.side_effect = mock_mv_filter
        mock_mlmodelversion.objects.create.side_effect = [mock_if_mv, mock_rf_mv]

        mock_mlmodeltype = MagicMock()
        mock_mlmodeltype.ISOLATION_FOREST = "ISOLATION_FOREST"
        mock_mlmodeltype.RANDOM_FOREST = "RANDOM_FOREST"

        mock_auditlog = MagicMock()
        mock_eventtype = MagicMock()
        mock_eventtype.MODEL_RETRAINED = "MODEL_RETRAINED"

        def mock_get_models():
            return {
                "AuditLog": mock_auditlog,
                "EventType": mock_eventtype,
                "Bid": MagicMock(),
                "CompanyProfile": MagicMock(),
                "FraudRiskScore": MagicMock(),
                "Tender": MagicMock(
                    objects=MagicMock(
                        prefetch_related=MagicMock(
                            return_value=MagicMock(all=MagicMock(return_value=[mock_tender] * 15))
                        )
                    )
                ),
                "MLModelType": mock_mlmodeltype,
                "MLModelVersion": mock_mlmodelversion,
            }

        monkeypatch.setattr(tasks_module, "_get_models", mock_get_models)

        # Patch train functions to return pre-trained results
        monkeypatch.setattr(tasks_module, "train_isolation_forest", lambda df, **kw: if_result)
        monkeypatch.setattr(tasks_module, "train_random_forest", lambda df, labels, **kw: rf_result)

        # Patch transaction.atomic to be a no-op context manager
        from unittest.mock import patch as _patch
        import django.db.transaction as _tx
        with _patch.object(_tx, "atomic", return_value=MagicMock(__enter__=MagicMock(return_value=None), __exit__=MagicMock(return_value=False))):
            result = tasks_module.retrain_models()

        assert result["status"] == "ok"
        assert result["isolation_forest_version"] == if_result.version
        assert result["random_forest_version"] == rf_result.version
        # Both model types should have been deactivated
        assert "ISOLATION_FOREST" in deactivated_types
        assert "RANDOM_FOREST" in deactivated_types

    def test_retrain_models_skips_when_insufficient_data(self, tmp_model_dir, monkeypatch):
        """retrain_models() returns 'skipped' when fewer than 10 labeled samples."""
        import ml_worker.tasks as tasks_module

        # Return only 5 tenders (all with < 3 bids → feature vector = None)
        mock_tender = MagicMock()
        mock_tender.bids.all.return_value = []  # 0 bids → skipped
        mock_tender.red_flags.filter.return_value.exists.return_value = False

        def mock_get_models():
            return {
                "AuditLog": MagicMock(),
                "EventType": MagicMock(),
                "Bid": MagicMock(),
                "CompanyProfile": MagicMock(),
                "FraudRiskScore": MagicMock(),
                "Tender": MagicMock(
                    objects=MagicMock(
                        prefetch_related=MagicMock(
                            return_value=MagicMock(all=MagicMock(return_value=[mock_tender] * 5))
                        )
                    )
                ),
                "MLModelType": MagicMock(),
                "MLModelVersion": MagicMock(),
            }

        monkeypatch.setattr(tasks_module, "_get_models", mock_get_models)

        result = tasks_module.retrain_models()
        assert result["status"] == "skipped"
        assert result["reason"] == "insufficient_data"
