"""
SHAP explainability service for TenderShield.

compute_shap(tender_id, model_version)
    Compute per-feature SHAP values for a tender using:
      - TreeExplainer for the Random Forest model (fast, exact)
      - KernelExplainer fallback for the Isolation Forest model (approximate)
    Stores results in a SHAPExplanation record.

    On any exception:
      - Sets shap_failed = True on the SHAPExplanation record
      - Logs a SHAP_FAILED event to AuditLog
      - Returns a fallback explanation built from active RedFlags only

CONTRACT:
  - Returns a dict with keys: shap_values, top_factors, shap_failed,
    model_version, rule_engine_version
  - top_factors is a list of up to 5 dicts sorted by absolute SHAP magnitude
  - shap_values maps feature name -> float (one entry per FEATURE_COLUMN)
  - This module makes Django ORM calls; it must be imported after Django setup
"""

from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from ml_worker.train import (
    FEATURE_COLUMNS,
    load_isolation_forest,
    load_random_forest,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rule engine version — bumped when RuleDefinition schema changes
# ---------------------------------------------------------------------------
RULE_ENGINE_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Plain-language templates keyed by feature name
# ---------------------------------------------------------------------------
PLAIN_LANGUAGE_TEMPLATES: dict[str, str] = {
    "cv_bids": (
        "The coefficient of variation of bids was {value:.3f}, indicating "
        "{direction} spread among submitted bids."
    ),
    "bid_spread_ratio": (
        "The ratio of the highest to lowest bid was {value:.2f}x, suggesting "
        "{direction} variation in bid amounts."
    ),
    "norm_winning_distance": (
        "The winning bid was {abs_value:.2f} standard deviations {direction} "
        "the mean bid amount."
    ),
    "single_bidder_flag": (
        "Only a single bidder submitted a bid for this tender."
    ),
    "price_deviation_pct": (
        "The winning bid deviated {abs_pct:.1f}% {direction} the estimated value."
    ),
    "deadline_days": (
        "The tender had only {value:.0f} day(s) between publication and the "
        "submission deadline."
    ),
    "repeat_winner_rate": (
        "The winning bidder has won {pct:.1f}% of tenders in this category "
        "over the past 12 months."
    ),
    "bidder_count": (
        "Only {value:.0f} bidder(s) participated in this tender."
    ),
    "winner_bid_rank": (
        "The winning bid ranked {value:.0f} out of all submitted bids "
        "(1 = lowest price)."
    ),
}


def _render_template(feature: str, shap_value: float, feature_value: float) -> str:
    """Render a plain-language sentence for a feature contribution."""
    tmpl = PLAIN_LANGUAGE_TEMPLATES.get(feature, f"Feature '{feature}' contributed {shap_value:+.4f} to the score.")

    direction_pos = "above" if feature_value >= 0 else "below"
    direction_high = "high" if feature_value >= 0 else "low"

    try:
        if feature == "cv_bids":
            return tmpl.format(value=feature_value, direction=direction_high)
        elif feature == "bid_spread_ratio":
            return tmpl.format(value=feature_value, direction=direction_high)
        elif feature == "norm_winning_distance":
            return tmpl.format(
                abs_value=abs(feature_value),
                direction="above" if feature_value >= 0 else "below",
            )
        elif feature == "single_bidder_flag":
            return tmpl  # static sentence
        elif feature == "price_deviation_pct":
            return tmpl.format(
                abs_pct=abs(feature_value * 100),
                direction="above" if feature_value >= 0 else "below",
            )
        elif feature == "deadline_days":
            return tmpl.format(value=feature_value)
        elif feature == "repeat_winner_rate":
            return tmpl.format(pct=feature_value * 100)
        elif feature == "bidder_count":
            return tmpl.format(value=feature_value)
        elif feature == "winner_bid_rank":
            return tmpl.format(value=feature_value)
        else:
            return tmpl
    except (KeyError, ValueError):
        return f"Feature '{feature}' had a SHAP contribution of {shap_value:+.4f}."


def _derive_top_factors(
    shap_values: dict[str, float],
    feature_vector: dict[str, float],
    n: int = 5,
) -> list[dict]:
    """Return top-n factors sorted by absolute SHAP magnitude.

    Each factor dict contains:
      - feature: str
      - shap_value: float
      - feature_value: float
      - explanation: str (plain-language sentence)
    """
    sorted_features = sorted(
        shap_values.keys(),
        key=lambda f: abs(shap_values[f]),
        reverse=True,
    )
    top = []
    for feature in sorted_features[:n]:
        sv = shap_values[feature]
        fv = feature_vector.get(feature, 0.0)
        top.append({
            "feature": feature,
            "shap_value": sv,
            "feature_value": fv,
            "explanation": _render_template(feature, sv, fv),
        })
    return top


def _get_django_models():
    """Lazily import Django models to avoid circular imports."""
    from audit.models import AuditLog, EventType
    from bids.models import Bid
    from detection.models import RedFlag
    from xai.models import MLModelType, MLModelVersion, SHAPExplanation

    return {
        "AuditLog": AuditLog,
        "EventType": EventType,
        "Bid": Bid,
        "RedFlag": RedFlag,
        "MLModelType": MLModelType,
        "MLModelVersion": MLModelVersion,
        "SHAPExplanation": SHAPExplanation,
    }


def _build_feature_vector_for_tender(tender, bids) -> Optional[dict]:
    """Build the 9-feature vector for a tender (delegates to feature_engineering)."""
    from companies.models import CompanyProfile
    from ml_worker.services.feature_engineering import compute_bid_screens

    win_rate = 0.0
    winner_bids = [b for b in bids if b.is_winner]
    if winner_bids:
        try:
            profile = CompanyProfile.objects.filter(bidder=winner_bids[0].bidder).first()
            if profile:
                win_rate = float(profile.win_rate or 0.0)
        except Exception:
            pass

    bid_dicts = [
        {
            "bid_amount": b.bid_amount,
            "is_winner": b.is_winner,
            "submission_timestamp": b.submission_timestamp,
            "bidder_id": str(b.bidder_id),
        }
        for b in bids
    ]
    tender_dict = {
        "estimated_value": tender.estimated_value,
        "submission_deadline": tender.submission_deadline,
        "publication_date": getattr(tender, "publication_date", None),
        "category": tender.category,
        "id": tender.id,
    }
    return compute_bid_screens(bid_dicts, tender_dict, win_rate)


def _compute_rf_shap(rf_model, feature_vector: dict) -> dict[str, float]:
    """Compute SHAP values using TreeExplainer for a Random Forest model."""
    import shap

    X = np.array([[feature_vector[col] for col in FEATURE_COLUMNS]], dtype=float)
    explainer = shap.TreeExplainer(rf_model)
    shap_vals = explainer.shap_values(X)

    # shap_values returns list[array] for multi-class; take class-1 (fraud)
    if isinstance(shap_vals, list):
        values = shap_vals[1][0] if len(shap_vals) > 1 else shap_vals[0][0]
    else:
        values = shap_vals[0]

    return {col: float(values[i]) for i, col in enumerate(FEATURE_COLUMNS)}


def _compute_if_shap_kernel(if_model, if_scaler, feature_vector: dict, background_data: Optional[np.ndarray] = None) -> dict[str, float]:
    """Compute SHAP values using KernelExplainer for an Isolation Forest model."""
    import shap

    X = np.array([[feature_vector[col] for col in FEATURE_COLUMNS]], dtype=float)

    # Use a small background dataset (zeros if none provided)
    if background_data is None:
        background_data = np.zeros((1, len(FEATURE_COLUMNS)))

    def _predict_fn(data: np.ndarray) -> np.ndarray:
        """Wrapper: returns normalized anomaly score for each row."""
        raw = -if_model.score_samples(data)
        scaled = if_scaler.transform(raw.reshape(-1, 1)).flatten()
        return np.clip(scaled, 0.0, 1.0)

    explainer = shap.KernelExplainer(_predict_fn, background_data)
    shap_vals = explainer.shap_values(X, nsamples=100, silent=True)

    if isinstance(shap_vals, list):
        values = shap_vals[0]
    else:
        values = shap_vals

    if values.ndim == 2:
        values = values[0]

    return {col: float(values[i]) for i, col in enumerate(FEATURE_COLUMNS)}


def _fallback_explanation(tender) -> dict:
    """Build a red-flag-only explanation when SHAP computation fails."""
    from detection.models import RedFlag

    red_flags = list(
        RedFlag.objects.filter(tender=tender, is_active=True)
        .values("flag_type", "severity", "trigger_data", "rule_version")
    )
    return {
        "shap_values": {},
        "top_factors": [],
        "red_flags": red_flags,
        "shap_failed": True,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_shap(
    tender_id: int,
    model_version: str,
    rule_engine_version: str = RULE_ENGINE_VERSION,
) -> dict:
    """Compute SHAP values for a tender and persist a SHAPExplanation record.

    Parameters
    ----------
    tender_id:
        Primary key of the Tender to explain.
    model_version:
        Combined model version string (e.g. "IF:20240101T120000-abc/RF:20240101T120000-def").
        Used to look up the correct model artifacts.
    rule_engine_version:
        Version of the rule engine used for this scoring run (default: RULE_ENGINE_VERSION).

    Returns
    -------
    dict with keys:
        shap_values: dict[str, float]  — one entry per FEATURE_COLUMN (empty on failure)
        top_factors: list[dict]        — up to 5 factors sorted by |SHAP| (empty on failure)
        red_flags: list[dict]          — all active RedFlags for the tender
        shap_failed: bool
        model_version: str
        rule_engine_version: str
        explanation_id: int            — PK of the created SHAPExplanation row
    """
    m = _get_django_models()
    SHAPExplanation = m["SHAPExplanation"]
    MLModelVersion = m["MLModelVersion"]
    MLModelType = m["MLModelType"]
    AuditLog = m["AuditLog"]
    EventType = m["EventType"]
    Bid = m["Bid"]

    from tenders.models import Tender

    try:
        tender = Tender.objects.get(pk=tender_id)
    except Tender.DoesNotExist:
        logger.error("compute_shap: Tender %s not found.", tender_id)
        return {
            "shap_values": {},
            "top_factors": [],
            "red_flags": [],
            "shap_failed": True,
            "model_version": model_version,
            "rule_engine_version": rule_engine_version,
            "explanation_id": None,
        }

    bids = list(Bid.objects.filter(tender=tender).select_related("bidder"))

    # Collect active red flags for inclusion in all responses
    from detection.models import RedFlag
    red_flags = list(
        RedFlag.objects.filter(tender=tender, is_active=True)
        .values("flag_type", "severity", "trigger_data", "rule_version")
    )

    # Build feature vector
    feature_vector = _build_feature_vector_for_tender(tender, bids)

    if feature_vector is None:
        # Fewer than 3 bids — no ML scores, no SHAP
        explanation = SHAPExplanation.objects.create(
            tender=tender,
            model_version=model_version,
            rule_engine_version=rule_engine_version,
            shap_values={},
            top_factors=[],
            shap_failed=True,
        )
        return {
            "shap_values": {},
            "top_factors": [],
            "red_flags": red_flags,
            "shap_failed": True,
            "model_version": model_version,
            "rule_engine_version": rule_engine_version,
            "explanation_id": explanation.pk,
        }

    # Load active model versions
    rf_version_obj = (
        MLModelVersion.objects.filter(model_type=MLModelType.RANDOM_FOREST, is_active=True)
        .order_by("-trained_at")
        .first()
    )
    if_version_obj = (
        MLModelVersion.objects.filter(model_type=MLModelType.ISOLATION_FOREST, is_active=True)
        .order_by("-trained_at")
        .first()
    )

    shap_values: dict[str, float] = {}
    shap_failed = False
    failure_reason = ""

    # --- Attempt TreeExplainer on Random Forest (primary) ---
    if rf_version_obj is not None:
        try:
            rf_model = load_random_forest(rf_version_obj.model_artifact_path)
            shap_values = _compute_rf_shap(rf_model, feature_vector)
        except Exception as exc:
            logger.warning(
                "compute_shap: TreeExplainer failed for Tender %s: %s. "
                "Falling back to KernelExplainer on Isolation Forest.",
                tender_id,
                exc,
            )
            shap_values = {}
            failure_reason = str(exc)

    # --- Fallback: KernelExplainer on Isolation Forest ---
    if not shap_values and if_version_obj is not None:
        try:
            if_model, if_scaler = load_isolation_forest(if_version_obj.model_artifact_path)
            shap_values = _compute_if_shap_kernel(if_model, if_scaler, feature_vector)
        except Exception as exc:
            logger.error(
                "compute_shap: KernelExplainer also failed for Tender %s: %s.",
                tender_id,
                exc,
            )
            shap_values = {}
            shap_failed = True
            failure_reason = str(exc)

    # If both explainers failed (or no models available), mark as failed
    if not shap_values:
        shap_failed = True

    # Derive top-5 factors
    top_factors: list[dict] = []
    if shap_values:
        top_factors = _derive_top_factors(shap_values, feature_vector, n=5)

    # Persist SHAPExplanation
    explanation = SHAPExplanation.objects.create(
        tender=tender,
        model_version=model_version,
        rule_engine_version=rule_engine_version,
        shap_values=shap_values,
        top_factors=top_factors,
        shap_failed=shap_failed,
    )

    # Log failure to AuditLog if SHAP failed
    if shap_failed:
        try:
            AuditLog.objects.create(
                event_type=EventType.SHAP_FAILED,
                user=None,
                affected_entity_type="Tender",
                affected_entity_id=str(tender_id),
                data_snapshot={
                    "tender_id": tender_id,
                    "model_version": model_version,
                    "rule_engine_version": rule_engine_version,
                    "reason": failure_reason,
                },
            )
        except Exception:
            logger.exception("compute_shap: Failed to write SHAP_FAILED AuditLog entry.")

    return {
        "shap_values": shap_values,
        "top_factors": top_factors,
        "red_flags": red_flags,
        "shap_failed": shap_failed,
        "model_version": model_version,
        "rule_engine_version": rule_engine_version,
        "explanation_id": explanation.pk,
    }
