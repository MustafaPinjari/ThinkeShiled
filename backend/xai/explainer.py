"""
XAIExplainer — generates SHAP-based and red-flag-only explanations for tenders.

Satisfies Requirements 6.1–6.6.
"""

from __future__ import annotations

import logging

from audit.models import AuditLog, EventType
from detection.models import RedFlag, RuleDefinition
from xai.models import SHAPExplanation

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Feature → plain-language template mapping
# ---------------------------------------------------------------------------

# Each template receives a dict of values extracted from the SHAP factor entry.
# Keys available: feature_value, shap_value, tender (the Tender ORM object).
FEATURE_TEMPLATES: dict[str, str] = {
    "price_deviation_pct": "Winning bid was {pct:.0f}% {direction} the estimated value.",
    "norm_winning_distance": "Winning bid was {pct:.0f}% {direction} the market average.",
    "bidder_count": "Only {n:.0f} bidder(s) submitted bids for this tender.",
    "single_bidder_flag": "This tender had only a single bidder.",
    "cv_bids": "Bid amounts were suspiciously {spread} (coefficient of variation: {val:.2f}).",
    "bid_spread_ratio": "The spread between highest and lowest bid was {val:.2f}x.",
    "repeat_winner_rate": "The winning bidder has won {pct:.0f}% of tenders in this category in the past 12 months.",
    "deadline_days": "The submission deadline was only {n:.0f} day(s) after publication.",
    "winner_bid_rank": "The winning bid ranked {rank} among all submitted bids.",
}


def _render_template(feature: str, feature_value: float) -> str:
    """Render a plain-language sentence for a given feature and its value."""
    if feature == "price_deviation_pct":
        pct = abs(feature_value * 100)
        direction = "below" if feature_value < 0 else "above"
        return f"Winning bid was {pct:.0f}% {direction} the estimated value."

    if feature == "norm_winning_distance":
        pct = abs(feature_value * 100)
        direction = "below" if feature_value < 0 else "above"
        return f"Winning bid was {pct:.0f}% {direction} the market average."

    if feature == "bidder_count":
        return f"Only {int(feature_value)} bidder(s) submitted bids for this tender."

    if feature == "single_bidder_flag":
        return "This tender had only a single bidder."

    if feature == "cv_bids":
        spread = "close together" if feature_value < 0.1 else "spread out"
        return f"Bid amounts were suspiciously {spread} (coefficient of variation: {feature_value:.2f})."

    if feature == "bid_spread_ratio":
        return f"The spread between highest and lowest bid was {feature_value:.2f}x."

    if feature == "repeat_winner_rate":
        pct = feature_value * 100
        return f"The winning bidder has won {pct:.0f}% of tenders in this category in the past 12 months."

    if feature == "deadline_days":
        return f"The submission deadline was only {int(feature_value)} day(s) after publication."

    if feature == "winner_bid_rank":
        rank = int(feature_value)
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(rank if rank <= 3 else 0, "th")
        return f"The winning bid ranked {rank}{suffix} among all submitted bids."

    # Fallback for unknown features
    return f"Feature '{feature}' had value {feature_value:.4f}."


def _build_red_flag_list(tender_id: int) -> list[dict]:
    """
    Return all active RedFlags for the tender, enriched with rule text.

    Each entry contains:
      - id, flag_type, severity, rule_version, trigger_data, raised_at
      - rule_text: the RuleDefinition.description for this flag_type (if found)
    """
    flags = (
        RedFlag.objects
        .filter(tender_id=tender_id, is_active=True)
        .order_by("-raised_at")
    )

    # Build a map of flag_type → rule description (active rules only)
    rule_map: dict[str, str] = {
        r.rule_code: r.description
        for r in RuleDefinition.objects.filter(is_active=True)
    }

    result = []
    for flag in flags:
        result.append({
            "id": flag.id,
            "flag_type": flag.flag_type,
            "severity": flag.severity,
            "rule_version": flag.rule_version,
            "trigger_data": flag.trigger_data,
            "raised_at": flag.raised_at.isoformat() if flag.raised_at else None,
            "rule_text": rule_map.get(flag.flag_type, ""),
        })
    return result


class XAIExplainer:
    """
    Generates SHAP-based and red-flag-only explanations for tenders.

    Usage:
        explainer = XAIExplainer()
        explanation = explainer.explain(tender_id=42, model_version="RF:v1")
    """

    def explain(self, tender_id: int, model_version: str) -> dict:
        """
        Generate a full explanation for a tender.

        Steps:
        1. Fetch the latest SHAPExplanation for the tender (filtered by model_version
           if provided, otherwise the most recent).
        2. If shap_failed=True on the stored explanation, delegate to fallback_explain().
        3. Map top_factors SHAP values to plain-language sentences.
        4. Fetch all active RedFlags with rule text and trigger data.
        5. Write an EXPLANATION_GENERATED AuditLog entry.
        6. Return structured explanation dict.

        Satisfies Requirements 6.1, 6.2, 6.4, 6.5.
        """
        from tenders.models import Tender

        try:
            tender = Tender.objects.get(pk=tender_id)
        except Tender.DoesNotExist:
            logger.warning("XAIExplainer.explain: tender_id=%s not found", tender_id)
            return {"error": "Tender not found"}

        # Fetch the latest SHAPExplanation (optionally filtered by model_version)
        qs = SHAPExplanation.objects.filter(tender=tender)
        if model_version:
            versioned = qs.filter(model_version=model_version).order_by("-computed_at").first()
            shap_exp = versioned or qs.order_by("-computed_at").first()
        else:
            shap_exp = qs.order_by("-computed_at").first()

        # If no SHAP explanation exists or SHAP failed, use fallback
        if shap_exp is None or shap_exp.shap_failed:
            return self.fallback_explain(tender_id)

        # Build plain-language top-5 factors
        plain_factors = self._build_plain_factors(shap_exp.top_factors)

        # Fetch active red flags with rule text
        red_flags = _build_red_flag_list(tender_id)

        explanation = {
            "tender_id": tender_id,
            "model_version": shap_exp.model_version,
            "rule_engine_version": shap_exp.rule_engine_version,
            "shap_values": shap_exp.shap_values,
            "top_factors": plain_factors,
            "red_flags": red_flags,
            "shap_failed": False,
            "computed_at": shap_exp.computed_at.isoformat() if shap_exp.computed_at else None,
        }

        # Write audit log entry (Requirement 6.5)
        self._write_audit_log(tender, explanation)

        return explanation

    def fallback_explain(self, tender_id: int) -> dict:
        """
        Return a red-flag-only explanation when SHAP computation has failed.

        Satisfies Requirement 6.6.
        """
        from tenders.models import Tender

        try:
            tender = Tender.objects.get(pk=tender_id)
        except Tender.DoesNotExist:
            logger.warning("XAIExplainer.fallback_explain: tender_id=%s not found", tender_id)
            return {"error": "Tender not found"}

        red_flags = _build_red_flag_list(tender_id)

        # Try to get version info from the (failed) SHAP explanation if available
        shap_exp = (
            SHAPExplanation.objects.filter(tender=tender)
            .order_by("-computed_at")
            .first()
        )
        model_version = shap_exp.model_version if shap_exp else ""
        rule_engine_version = shap_exp.rule_engine_version if shap_exp else ""
        computed_at = shap_exp.computed_at.isoformat() if shap_exp and shap_exp.computed_at else None

        explanation = {
            "tender_id": tender_id,
            "model_version": model_version,
            "rule_engine_version": rule_engine_version,
            "shap_values": {},
            "top_factors": [],
            "red_flags": red_flags,
            "shap_failed": True,
            "computed_at": computed_at,
        }

        # Write audit log entry
        self._write_audit_log(tender, explanation)

        return explanation

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_plain_factors(self, top_factors: list) -> list[dict]:
        """
        Convert raw top_factors (from SHAPExplanation.top_factors) into
        plain-language sentences.

        Each input entry is expected to have:
          { "feature": str, "shap_value": float, "feature_value": float, ... }

        Returns at most 5 entries, each with an added "explanation" key.
        """
        result = []
        for factor in top_factors[:5]:
            feature = factor.get("feature", "")
            feature_value = factor.get("feature_value", 0.0)
            shap_value = factor.get("shap_value", 0.0)

            sentence = _render_template(feature, feature_value)

            result.append({
                "feature": feature,
                "shap_value": shap_value,
                "feature_value": feature_value,
                "explanation": sentence,
            })
        return result

    def _write_audit_log(self, tender, explanation: dict) -> None:
        """Write an EXPLANATION_GENERATED audit log entry."""
        try:
            AuditLog.objects.create(
                event_type=EventType.EXPLANATION_GENERATED,
                affected_entity_type="Tender",
                affected_entity_id=str(tender.tender_id),
                data_snapshot={
                    "action": "explanation_generated",
                    "model_version": explanation.get("model_version", ""),
                    "rule_engine_version": explanation.get("rule_engine_version", ""),
                    "shap_failed": explanation.get("shap_failed", False),
                    "red_flag_count": len(explanation.get("red_flags", [])),
                },
            )
        except Exception:
            logger.exception(
                "Failed to write audit log for explanation of tender_id=%s",
                tender.pk,
            )
