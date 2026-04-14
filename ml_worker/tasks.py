"""
Celery tasks for the TenderShield ML worker.

Tasks
-----
score_tender(tender_id)
    Load active IF + RF models, compute feature vector for the tender,
    write ml_anomaly_score and ml_collusion_score to the latest
    FraudRiskScore row, and insert MLModelVersion records if needed.

retrain_models()
    Scheduled Celery beat task.  Loads all labeled tenders, retrains
    both models, inserts new MLModelVersion records, deactivates the
    previous versions, and writes an AuditLog entry.
    Minimum interval: ML_RETRAIN_INTERVAL_HOURS (default 24 h).
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import django

# Bootstrap Django so ORM is available when the worker imports this module.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Only call django.setup() when running as a Celery worker process.
# When imported in unit tests (which mock the ORM), Django may already be
# configured or the config module may not be on sys.path.
def _bootstrap_django():
    try:
        from django.conf import settings as _s
        if not _s.configured:
            django.setup()
        elif not _s.INSTALLED_APPS:
            # Minimally configured (e.g., in tests) — skip full setup
            pass
    except Exception:
        pass  # Running outside Django context (e.g., pure unit tests)

_bootstrap_django()

import pandas as pd
from celery import shared_task
from celery.schedules import crontab
from django.conf import settings
from django.db import transaction
from django.utils import timezone as dj_timezone

from ml_worker.services.feature_engineering import compute_bid_screens
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers — Django ORM imports (deferred to avoid circular imports at module
# load time when Django is not yet fully initialised)
# ---------------------------------------------------------------------------

def _get_models():
    """Return Django model classes (imported lazily)."""
    from audit.models import AuditLog, EventType
    from bids.models import Bid
    from companies.models import CompanyProfile
    from scoring.models import FraudRiskScore
    from tenders.models import Tender
    from xai.models import MLModelType, MLModelVersion

    return {
        "AuditLog": AuditLog,
        "EventType": EventType,
        "Bid": Bid,
        "CompanyProfile": CompanyProfile,
        "FraudRiskScore": FraudRiskScore,
        "Tender": Tender,
        "MLModelType": MLModelType,
        "MLModelVersion": MLModelVersion,
    }


def _get_active_model_version(MLModelVersion, MLModelType, model_type_value: str):
    """Return the active MLModelVersion for the given model type, or None."""
    return (
        MLModelVersion.objects.filter(
            model_type=model_type_value,
            is_active=True,
        )
        .order_by("-trained_at")
        .first()
    )


def _build_feature_vector(tender, bids) -> dict | None:
    """Build the 9-feature vector for a tender.

    Returns None when bid count < 3 (per Requirement 4.5).
    """
    # Determine winning bidder's win rate in this category
    win_rate = 0.0
    winner_bids = [b for b in bids if b.is_winner]
    if winner_bids:
        winner_bidder = winner_bids[0].bidder
        try:
            from companies.models import CompanyProfile
            profile = CompanyProfile.objects.filter(bidder=winner_bidder).first()
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
        "publication_date": tender.publication_date,
        "category": tender.category,
        "id": tender.id,
    }
    return compute_bid_screens(bid_dicts, tender_dict, win_rate)


# ---------------------------------------------------------------------------
# 10.3 — score_tender Celery task
# ---------------------------------------------------------------------------

@shared_task(name="ml_worker.score_tender", bind=True, max_retries=3, default_retry_delay=30)
def score_tender(self, tender_id: int) -> dict:
    """Compute ML scores for a tender and persist to FraudRiskScore.

    Steps
    -----
    1. Load the tender and its bids from the DB.
    2. Compute the 9-feature vector via feature_engineering.
    3. If bid count < 3, set both ML scores to null and return early.
    4. Load the active IsolationForest and RandomForest model artifacts.
    5. Run inference; clamp outputs to [0, 1].
    6. Update the latest FraudRiskScore row with ml_anomaly_score and
       ml_collusion_score (or create a new row if none exists).
    7. Return a summary dict.
    """
    m = _get_models()
    Tender = m["Tender"]
    Bid = m["Bid"]
    FraudRiskScore = m["FraudRiskScore"]
    MLModelVersion = m["MLModelVersion"]
    MLModelType = m["MLModelType"]

    try:
        tender = Tender.objects.get(pk=tender_id)
    except Tender.DoesNotExist:
        logger.error("score_tender: Tender %s not found.", tender_id)
        return {"error": f"Tender {tender_id} not found"}

    bids = list(Bid.objects.filter(tender=tender).select_related("bidder"))

    # Build feature vector — returns None when bid count < 3
    feature_vector = _build_feature_vector(tender, bids)

    if feature_vector is None:
        # Per Requirement 4.5: fewer than 3 bids → ML scores are null
        logger.info(
            "score_tender: Tender %s has %d bids (<3); ML scores set to null.",
            tender_id,
            len(bids),
        )
        _upsert_fraud_risk_score(
            FraudRiskScore,
            tender,
            ml_anomaly_score=None,
            ml_collusion_score=None,
            model_version="",
        )
        return {"tender_id": tender_id, "ml_anomaly_score": None, "ml_collusion_score": None}

    # Load active models
    if_version = _get_active_model_version(MLModelVersion, MLModelType, "ISOLATION_FOREST")
    rf_version = _get_active_model_version(MLModelVersion, MLModelType, "RANDOM_FOREST")

    if if_version is None or rf_version is None:
        logger.warning(
            "score_tender: No active ML models found for Tender %s. "
            "Scores set to null.",
            tender_id,
        )
        _upsert_fraud_risk_score(
            FraudRiskScore,
            tender,
            ml_anomaly_score=None,
            ml_collusion_score=None,
            model_version="",
        )
        return {"tender_id": tender_id, "ml_anomaly_score": None, "ml_collusion_score": None}

    try:
        if_model, if_scaler = load_isolation_forest(if_version.model_artifact_path)
        rf_model = load_random_forest(rf_version.model_artifact_path)
    except Exception as exc:
        logger.exception("score_tender: Failed to load model artifacts for Tender %s.", tender_id)
        raise self.retry(exc=exc)

    # Run inference
    ml_anomaly_score = predict_anomaly_score(if_model, if_scaler, feature_vector)
    ml_collusion_score = predict_collusion_score(rf_model, feature_vector)

    combined_version = f"IF:{if_version.version}/RF:{rf_version.version}"

    _upsert_fraud_risk_score(
        FraudRiskScore,
        tender,
        ml_anomaly_score=ml_anomaly_score,
        ml_collusion_score=ml_collusion_score,
        model_version=combined_version,
    )

    logger.info(
        "score_tender: Tender %s scored — anomaly=%.4f collusion=%.4f",
        tender_id,
        ml_anomaly_score,
        ml_collusion_score,
    )
    return {
        "tender_id": tender_id,
        "ml_anomaly_score": ml_anomaly_score,
        "ml_collusion_score": ml_collusion_score,
        "model_version": combined_version,
    }


def _upsert_fraud_risk_score(
    FraudRiskScore,
    tender,
    ml_anomaly_score,
    ml_collusion_score,
    model_version: str,
) -> None:
    """Update the latest FraudRiskScore row with ML scores, or create one."""
    with transaction.atomic():
        latest = (
            FraudRiskScore.objects.select_for_update()
            .filter(tender=tender)
            .order_by("-computed_at")
            .first()
        )
        if latest is not None:
            latest.ml_anomaly_score = ml_anomaly_score
            latest.ml_collusion_score = ml_collusion_score
            if model_version:
                latest.model_version = model_version
            latest.computed_at = dj_timezone.now()
            latest.save(update_fields=["ml_anomaly_score", "ml_collusion_score", "model_version", "computed_at"])
        else:
            # No score row yet — create a minimal one (rule-based score = 0)
            FraudRiskScore.objects.create(
                tender=tender,
                score=0,
                ml_anomaly_score=ml_anomaly_score,
                ml_collusion_score=ml_collusion_score,
                red_flag_contribution=0,
                model_version=model_version,
            )


# ---------------------------------------------------------------------------
# 10.4 — Scheduled model retraining Celery beat task
# ---------------------------------------------------------------------------

@shared_task(name="ml_worker.retrain_models")
def retrain_models() -> dict:
    """Retrain IsolationForest and RandomForest on all labeled tender data.

    Steps
    -----
    1. Load all FraudRiskScore rows that have a label (is_fraudulent field on
       Tender, or a proxy: any tender with a HIGH-severity active RedFlag is
       treated as label=1, otherwise label=0).
    2. Compute feature vectors for each tender.
    3. Retrain both models.
    4. Insert new MLModelVersion records; deactivate previous active versions.
    5. Write an AuditLog entry with model version, training date, and feature
       importances.
    6. Return a summary dict.

    The minimum retraining interval is enforced by the Celery beat schedule
    (ML_RETRAIN_INTERVAL_HOURS, default 24 h).
    """
    m = _get_models()
    Tender = m["Tender"]
    Bid = m["Bid"]
    AuditLog = m["AuditLog"]
    EventType = m["EventType"]
    MLModelVersion = m["MLModelVersion"]
    MLModelType = m["MLModelType"]

    logger.info("retrain_models: Starting model retraining.")

    # ------------------------------------------------------------------
    # 1. Collect training data
    # ------------------------------------------------------------------
    tenders = list(Tender.objects.prefetch_related("bids__bidder", "red_flags").all())

    rows = []
    labels = []

    for tender in tenders:
        bids = list(tender.bids.all())
        fv = _build_feature_vector(tender, bids)
        if fv is None:
            continue  # skip tenders with < 3 bids

        # Label: 1 if any active HIGH-severity red flag, else 0
        has_high_flag = tender.red_flags.filter(
            is_active=True, severity="HIGH"
        ).exists()
        label = 1 if has_high_flag else 0

        rows.append(fv)
        labels.append(label)

    if len(rows) < 10:
        logger.warning(
            "retrain_models: Only %d labeled samples available. "
            "Skipping retraining (minimum 10 required).",
            len(rows),
        )
        return {"status": "skipped", "reason": "insufficient_data", "samples": len(rows)}

    feature_df = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    label_series = pd.Series(labels, name="label")

    # ------------------------------------------------------------------
    # 2. Train models
    # ------------------------------------------------------------------
    try:
        if_result: TrainedModel = train_isolation_forest(
            feature_df,
            contamination=float(getattr(settings, "ML_IF_CONTAMINATION", 0.05)),
        )
        rf_result: TrainedModel = train_random_forest(feature_df, label_series)
    except Exception:
        logger.exception("retrain_models: Training failed.")
        raise

    # ------------------------------------------------------------------
    # 3. Persist MLModelVersion records and deactivate old versions
    # ------------------------------------------------------------------
    with transaction.atomic():
        # Deactivate previous IF versions
        MLModelVersion.objects.filter(
            model_type=MLModelType.ISOLATION_FOREST, is_active=True
        ).update(is_active=False)

        if_mv = MLModelVersion.objects.create(
            model_type=MLModelType.ISOLATION_FOREST,
            version=if_result.version,
            trained_at=dj_timezone.now(),
            feature_importances=if_result.feature_importances,
            model_artifact_path=if_result.artifact_path,
            is_active=True,
        )

        # Deactivate previous RF versions
        MLModelVersion.objects.filter(
            model_type=MLModelType.RANDOM_FOREST, is_active=True
        ).update(is_active=False)

        rf_mv = MLModelVersion.objects.create(
            model_type=MLModelType.RANDOM_FOREST,
            version=rf_result.version,
            trained_at=dj_timezone.now(),
            feature_importances=rf_result.feature_importances,
            model_artifact_path=rf_result.artifact_path,
            is_active=True,
        )

        # ------------------------------------------------------------------
        # 4. Write AuditLog entry (Requirement 4.6)
        # ------------------------------------------------------------------
        AuditLog.objects.create(
            event_type=EventType.MODEL_RETRAINED,
            user=None,
            affected_entity_type="MLModelVersion",
            affected_entity_id=f"IF:{if_mv.id},RF:{rf_mv.id}",
            data_snapshot={
                "isolation_forest": {
                    "version": if_result.version,
                    "artifact_path": if_result.artifact_path,
                    "feature_importances": if_result.feature_importances,
                    "trained_at": dj_timezone.now().isoformat(),
                    "samples": len(rows),
                },
                "random_forest": {
                    "version": rf_result.version,
                    "artifact_path": rf_result.artifact_path,
                    "feature_importances": rf_result.feature_importances,
                    "trained_at": dj_timezone.now().isoformat(),
                    "samples": len(rows),
                },
            },
        )

    logger.info(
        "retrain_models: Complete. IF=%s RF=%s samples=%d",
        if_result.version,
        rf_result.version,
        len(rows),
    )
    return {
        "status": "ok",
        "isolation_forest_version": if_result.version,
        "random_forest_version": rf_result.version,
        "samples": len(rows),
    }
