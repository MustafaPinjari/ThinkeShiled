"""
RiskScorer — aggregates rule-based red flags and ML scores into a
single integer Fraud Risk Score in the range [0, 100].

Scoring formula (default weights):
    red_flag_contribution = min(50,
        HIGH_flags × 25 + MEDIUM_flags × 10
    )
    score = clamp(
        red_flag_contribution
        + ml_anomaly_score × 30
        + ml_collusion_score × 20,
        0, 100
    )

Custom weight overrides (stored in ScoringWeightConfig) replace the
defaults when an Administrator has configured them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from django.utils import timezone

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------ #
# Default weight constants                                             #
# ------------------------------------------------------------------ #

DEFAULT_HIGH_WEIGHT = 25
DEFAULT_MEDIUM_WEIGHT = 10
DEFAULT_RED_FLAG_CAP = 50
DEFAULT_ML_ANOMALY_WEIGHT = 30
DEFAULT_ML_COLLUSION_WEIGHT = 20


@dataclass
class ScoringWeights:
    """Holds the weight configuration for a single scoring run."""

    high_weight: int = DEFAULT_HIGH_WEIGHT
    medium_weight: int = DEFAULT_MEDIUM_WEIGHT
    red_flag_cap: int = DEFAULT_RED_FLAG_CAP
    ml_anomaly_weight: int = DEFAULT_ML_ANOMALY_WEIGHT
    ml_collusion_weight: int = DEFAULT_ML_COLLUSION_WEIGHT

    def to_dict(self) -> dict:
        return {
            "high_weight": self.high_weight,
            "medium_weight": self.medium_weight,
            "red_flag_cap": self.red_flag_cap,
            "ml_anomaly_weight": self.ml_anomaly_weight,
            "ml_collusion_weight": self.ml_collusion_weight,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ScoringWeights":
        return cls(
            high_weight=int(data.get("high_weight", DEFAULT_HIGH_WEIGHT)),
            medium_weight=int(data.get("medium_weight", DEFAULT_MEDIUM_WEIGHT)),
            red_flag_cap=int(data.get("red_flag_cap", DEFAULT_RED_FLAG_CAP)),
            ml_anomaly_weight=int(data.get("ml_anomaly_weight", DEFAULT_ML_ANOMALY_WEIGHT)),
            ml_collusion_weight=int(data.get("ml_collusion_weight", DEFAULT_ML_COLLUSION_WEIGHT)),
        )


class RiskScorer:
    """
    Computes and persists Fraud Risk Scores for tenders.

    Usage:
        scorer = RiskScorer()
        score_record = scorer.compute_score(tender_id)
        latest = scorer.get_score(tender_id)
    """

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    def compute_score(
        self,
        tender_id: int,
        weights: Optional[ScoringWeights] = None,
        user=None,
        ip_address: Optional[str] = None,
    ):
        """
        Compute and persist the fraud risk score for a tender.

        Steps:
          1. Load active red flags for the tender.
          2. Load the latest ML scores (ml_anomaly_score, ml_collusion_score).
          3. Resolve weight overrides (custom > passed-in > defaults).
          4. Apply the scoring formula and clamp to [0, 100].
          5. Persist a new FraudRiskScore row.
          6. Write an AuditLog entry.

        Returns the newly created FraudRiskScore instance.
        """
        from detection.models import RedFlag, Severity
        from scoring.models import FraudRiskScore
        from audit.models import AuditLog, EventType

        # 1. Resolve weights (custom config > caller-supplied > defaults)
        effective_weights = self._resolve_weights(tender_id, weights)

        # 2. Count active red flags by severity
        active_flags = list(
            RedFlag.objects.filter(tender_id=tender_id, is_active=True)
            .values("severity")
        )
        high_count = sum(1 for f in active_flags if f["severity"] == Severity.HIGH)
        medium_count = sum(1 for f in active_flags if f["severity"] == Severity.MEDIUM)

        # 3. Red flag contribution (capped)
        raw_flag_score = (
            high_count * effective_weights.high_weight
            + medium_count * effective_weights.medium_weight
        )
        red_flag_contribution = min(raw_flag_score, effective_weights.red_flag_cap)

        # 4. Fetch latest ML scores for this tender
        ml_anomaly, ml_collusion, model_version = self._get_latest_ml_scores(tender_id)

        # 5. Compute weighted ML contribution
        ml_contribution = 0.0
        if ml_anomaly is not None:
            ml_contribution += float(ml_anomaly) * effective_weights.ml_anomaly_weight
        if ml_collusion is not None:
            ml_contribution += float(ml_collusion) * effective_weights.ml_collusion_weight

        # 6. Final score clamped to [0, 100]
        raw_score = red_flag_contribution + ml_contribution
        final_score = max(0, min(100, int(round(raw_score))))

        # 7. Persist
        score_record = FraudRiskScore.objects.create(
            tender_id=tender_id,
            score=final_score,
            ml_anomaly_score=ml_anomaly,
            ml_collusion_score=ml_collusion,
            red_flag_contribution=red_flag_contribution,
            model_version=model_version,
            weight_config=effective_weights.to_dict(),
            computed_at=timezone.now(),
        )

        # 8. Audit log
        AuditLog.objects.create(
            event_type=EventType.SCORE_COMPUTED,
            user=user,
            affected_entity_type="Tender",
            affected_entity_id=str(tender_id),
            ip_address=ip_address,
            data_snapshot={
                "tender_id": tender_id,
                "score": final_score,
                "red_flag_contribution": red_flag_contribution,
                "high_flags": high_count,
                "medium_flags": medium_count,
                "ml_anomaly_score": str(ml_anomaly) if ml_anomaly is not None else None,
                "ml_collusion_score": str(ml_collusion) if ml_collusion is not None else None,
                "model_version": model_version,
                "weights": effective_weights.to_dict(),
            },
        )

        logger.info(
            "Computed score %d for tender_id=%d "
            "(flags: HIGH=%d MEDIUM=%d, ml_anomaly=%s, ml_collusion=%s)",
            final_score, tender_id, high_count, medium_count, ml_anomaly, ml_collusion,
        )
        return score_record

    def get_score(self, tender_id: int):
        """
        Return the latest FraudRiskScore row for a tender, or None if none exists.
        """
        from scoring.models import FraudRiskScore

        return (
            FraudRiskScore.objects.filter(tender_id=tender_id)
            .order_by("-computed_at")
            .first()
        )

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _resolve_weights(
        self,
        tender_id: int,
        caller_weights: Optional[ScoringWeights],
    ) -> ScoringWeights:
        """
        Priority: DB-stored ScoringWeightConfig > caller-supplied > defaults.
        """
        # Try to load a persisted custom config
        db_weights = self._load_weight_config(tender_id)
        if db_weights is not None:
            return db_weights
        if caller_weights is not None:
            return caller_weights
        return ScoringWeights()

    def _load_weight_config(self, tender_id: int) -> Optional[ScoringWeights]:
        """
        Load a ScoringWeightConfig from the DB if one exists.
        Returns None when no custom config is found.
        """
        try:
            from scoring.models import ScoringWeightConfig  # type: ignore[attr-defined]
            config = ScoringWeightConfig.objects.filter(is_active=True).order_by("-created_at").first()
            if config:
                return ScoringWeights.from_dict(config.weights)
        except Exception:
            # ScoringWeightConfig table may not exist yet; fall back to defaults
            pass
        return None

    def _get_latest_ml_scores(self, tender_id: int):
        """
        Return (ml_anomaly_score, ml_collusion_score, model_version) from the
        most recent FraudRiskScore row that has ML scores, or (None, None, "")
        if no ML scores are available yet.
        """
        from scoring.models import FraudRiskScore

        latest_with_ml = (
            FraudRiskScore.objects.filter(
                tender_id=tender_id,
                ml_anomaly_score__isnull=False,
            )
            .order_by("-computed_at")
            .first()
        )
        if latest_with_ml:
            return (
                latest_with_ml.ml_anomaly_score,
                latest_with_ml.ml_collusion_score,
                latest_with_ml.model_version,
            )
        return None, None, ""
