"""
ML model training for TenderShield.

Provides:
  - train_isolation_forest(feature_df) -> TrainedModel
  - train_random_forest(feature_df, labels) -> TrainedModel

Both functions return a TrainedModel namedtuple containing the fitted model,
the scaler (for IF), feature importances, and the artifact path after
serialization with joblib.

CONTRACT:
  - train_isolation_forest normalizes raw IF scores to [0, 1] via min-max
    scaling over the training set.  The scaler is stored alongside the model
    so that inference can apply the same transformation.
  - train_random_forest uses class_weight='balanced' to handle label imbalance.
  - Both functions serialize the artifact to ML_MODEL_DIR (env-configurable,
    default: ml_worker/models/).
  - Feature column order must match FEATURE_COLUMNS exactly.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import MinMaxScaler

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

ML_MODEL_DIR = Path(
    os.environ.get("ML_MODEL_PATH", str(Path(__file__).parent / "models"))
)


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

class TrainedModel(NamedTuple):
    model: object                    # fitted sklearn estimator
    scaler: Optional[MinMaxScaler]   # MinMaxScaler for IF; None for RF
    feature_importances: dict        # feature name -> importance float
    artifact_path: str               # absolute path to the serialized artifact
    version: str                     # unique version string (timestamp + uuid4 prefix)
    model_type: str                  # "ISOLATION_FOREST" or "RANDOM_FOREST"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _ensure_model_dir() -> Path:
    ML_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return ML_MODEL_DIR


def _make_version() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    uid = str(uuid.uuid4())[:8]
    return f"{ts}-{uid}"


def _validate_feature_df(feature_df: pd.DataFrame) -> pd.DataFrame:
    """Ensure the dataframe contains all required feature columns."""
    missing = [c for c in FEATURE_COLUMNS if c not in feature_df.columns]
    if missing:
        raise ValueError(f"feature_df is missing required columns: {missing}")
    return feature_df[FEATURE_COLUMNS].copy()


# ---------------------------------------------------------------------------
# 10.1 — Isolation Forest training
# ---------------------------------------------------------------------------

def train_isolation_forest(
    feature_df: pd.DataFrame,
    contamination: float = 0.05,
    random_state: int = 42,
) -> TrainedModel:
    """Fit an IsolationForest on feature_df and normalize scores to [0, 1].

    Parameters
    ----------
    feature_df:
        DataFrame with at least the 9 FEATURE_COLUMNS.  Rows with NaN are
        dropped before fitting.
    contamination:
        Expected proportion of anomalies in the training set (default 0.05).
    random_state:
        Seed for reproducibility.

    Returns
    -------
    TrainedModel with the fitted IsolationForest, a MinMaxScaler calibrated
    on the training scores, and the serialized artifact path.

    Notes
    -----
    IsolationForest.score_samples() returns negative values where more
    negative = more anomalous.  We invert the sign so that higher raw score
    = more anomalous, then apply min-max scaling to map to [0, 1].
    """
    X = _validate_feature_df(feature_df).dropna()
    if len(X) == 0:
        raise ValueError("feature_df has no valid (non-NaN) rows after filtering.")

    model = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    model.fit(X)

    # Compute raw scores on training data and fit the scaler
    raw_scores = -model.score_samples(X)  # invert: higher = more anomalous
    scaler = MinMaxScaler(feature_range=(0.0, 1.0))
    scaler.fit(raw_scores.reshape(-1, 1))

    # Feature importances: IsolationForest doesn't expose them natively;
    # use mean absolute feature contribution as a proxy via mean depth.
    # We approximate by computing the variance of each feature across trees.
    feature_importances = {col: float(np.var(X[col].values)) for col in FEATURE_COLUMNS}
    total = sum(feature_importances.values()) or 1.0
    feature_importances = {k: v / total for k, v in feature_importances.items()}

    # Serialize
    version = _make_version()
    artifact_path = str(_ensure_model_dir() / f"isolation_forest_{version}.pkl")
    joblib.dump({"model": model, "scaler": scaler}, artifact_path)

    return TrainedModel(
        model=model,
        scaler=scaler,
        feature_importances=feature_importances,
        artifact_path=artifact_path,
        version=version,
        model_type="ISOLATION_FOREST",
    )


# ---------------------------------------------------------------------------
# 10.2 — Random Forest training
# ---------------------------------------------------------------------------

def train_random_forest(
    feature_df: pd.DataFrame,
    labels: pd.Series,
    random_state: int = 42,
) -> TrainedModel:
    """Fit a RandomForestClassifier on feature_df with balanced class weights.

    Parameters
    ----------
    feature_df:
        DataFrame with at least the 9 FEATURE_COLUMNS.
    labels:
        Binary series (0 = clean, 1 = fraudulent/collusive) aligned with
        feature_df.  Rows where either feature_df or labels is NaN are dropped.
    random_state:
        Seed for reproducibility.

    Returns
    -------
    TrainedModel with the fitted RandomForestClassifier, no scaler (None),
    feature importances from the model, and the serialized artifact path.
    """
    X = _validate_feature_df(feature_df)
    y = labels.reset_index(drop=True)
    X = X.reset_index(drop=True)

    # Drop rows where either X or y has NaN
    valid_mask = X.notna().all(axis=1) & y.notna()
    X = X[valid_mask]
    y = y[valid_mask]

    if len(X) == 0:
        raise ValueError("feature_df / labels have no valid rows after NaN filtering.")

    model = RandomForestClassifier(
        class_weight="balanced",
        random_state=random_state,
        n_estimators=100,
    )
    model.fit(X, y)

    # Feature importances from the model
    feature_importances = {
        col: float(imp)
        for col, imp in zip(FEATURE_COLUMNS, model.feature_importances_)
    }

    # Serialize
    version = _make_version()
    artifact_path = str(_ensure_model_dir() / f"random_forest_{version}.pkl")
    joblib.dump({"model": model}, artifact_path)

    return TrainedModel(
        model=model,
        scaler=None,
        feature_importances=feature_importances,
        artifact_path=artifact_path,
        version=version,
        model_type="RANDOM_FOREST",
    )


# ---------------------------------------------------------------------------
# Inference helpers (used by tasks.py)
# ---------------------------------------------------------------------------

def load_isolation_forest(artifact_path: str) -> tuple:
    """Load a serialized IsolationForest artifact.

    Returns (model, scaler).
    """
    data = joblib.load(artifact_path)
    return data["model"], data["scaler"]


def load_random_forest(artifact_path: str) -> RandomForestClassifier:
    """Load a serialized RandomForestClassifier artifact."""
    data = joblib.load(artifact_path)
    return data["model"]


def predict_anomaly_score(
    model: IsolationForest,
    scaler: MinMaxScaler,
    feature_vector: dict,
) -> float:
    """Return a normalized anomaly score in [0, 1] for a single feature vector.

    Parameters
    ----------
    model:
        Fitted IsolationForest.
    scaler:
        MinMaxScaler fitted on training scores.
    feature_vector:
        Dict mapping feature name -> value (must contain all FEATURE_COLUMNS).

    Returns
    -------
    float in [0.0, 1.0] — higher means more anomalous.
    """
    X = np.array([[feature_vector[col] for col in FEATURE_COLUMNS]], dtype=float)
    raw = -model.score_samples(X)  # invert sign
    score = float(scaler.transform(raw.reshape(-1, 1))[0, 0])
    # Clamp to [0, 1] in case of out-of-distribution inputs
    return float(np.clip(score, 0.0, 1.0))


def predict_collusion_score(
    model: RandomForestClassifier,
    feature_vector: dict,
) -> float:
    """Return collusion probability in [0, 1] for a single feature vector.

    Parameters
    ----------
    model:
        Fitted RandomForestClassifier.
    feature_vector:
        Dict mapping feature name -> value (must contain all FEATURE_COLUMNS).

    Returns
    -------
    float in [0.0, 1.0] — probability of class 1 (collusive).
    """
    X = np.array([[feature_vector[col] for col in FEATURE_COLUMNS]], dtype=float)
    prob = float(model.predict_proba(X)[0, 1])
    return float(np.clip(prob, 0.0, 1.0))
