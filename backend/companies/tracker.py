"""
BehavioralTracker — maintains longitudinal company risk profiles.

Recomputes metrics for a bidder from raw bid/award/red-flag/score data
and persists the result to CompanyProfile.  Designed to run as a Celery
task so it completes within 10 seconds of bid/award ingestion.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Avg, Count, Max, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


class BehavioralTracker:
    """Compute and persist company risk profiles for bidders."""

    # Rolling window used for win-rate HIGH_RISK check (Requirement 7.3)
    ROLLING_WINDOW_DAYS = 365

    # Win-rate threshold that triggers HIGH_RISK per category (Requirement 7.3)
    HIGH_RISK_WIN_RATE_THRESHOLD = 0.60

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def update_profile(self, bidder_id: int) -> "CompanyProfile":
        """
        Recompute all metrics for *bidder_id* and persist to CompanyProfile.

        Returns the updated (or newly created) CompanyProfile instance.
        """
        from bids.models import Bid, Bidder
        from companies.models import CompanyProfile, RiskStatus
        from detection.models import RedFlag
        from scoring.models import FraudRiskScore

        try:
            bidder = Bidder.objects.get(pk=bidder_id)
        except Bidder.DoesNotExist:
            logger.error("BehavioralTracker.update_profile: Bidder %s not found", bidder_id)
            raise

        bids_qs = Bid.objects.filter(bidder=bidder)

        total_bids = bids_qs.count()
        total_wins = bids_qs.filter(is_winner=True).count()
        win_rate = (total_wins / total_bids) if total_bids > 0 else 0.0

        # avg_bid_deviation: mean of |(bid_amount - estimated_value) / estimated_value|
        avg_bid_deviation = self._compute_avg_bid_deviation(bids_qs)

        # active red flags linked to this bidder
        active_red_flag_count = RedFlag.objects.filter(
            bidder=bidder, is_active=True
        ).count()

        # highest fraud risk score across all tenders this bidder participated in
        tender_ids = bids_qs.values_list("tender_id", flat=True).distinct()
        score_agg = FraudRiskScore.objects.filter(
            tender_id__in=tender_ids
        ).aggregate(max_score=Max("score"))
        highest_fraud_risk_score = score_agg["max_score"] or 0

        with transaction.atomic():
            profile, _ = CompanyProfile.objects.get_or_create(bidder=bidder)
            profile.total_bids = total_bids
            profile.total_wins = total_wins
            profile.win_rate = round(win_rate, 4)
            profile.avg_bid_deviation = round(float(avg_bid_deviation), 4)
            profile.active_red_flag_count = active_red_flag_count
            profile.highest_fraud_risk_score = highest_fraud_risk_score
            # Preserve existing HIGH_RISK if already set; flag_high_risk() may
            # upgrade the status but update_profile() never downgrades it.
            if profile.risk_status != RiskStatus.HIGH_RISK:
                profile.risk_status = self._compute_risk_status(
                    bidder, win_rate, profile
                )
            profile.save()

        logger.info(
            "BehavioralTracker: updated profile for bidder %s (total_bids=%s, win_rate=%.4f)",
            bidder_id,
            total_bids,
            win_rate,
        )
        return profile

    def get_profile(self, bidder_id: int) -> "CompanyProfile":
        """Retrieve the current company risk profile for *bidder_id*."""
        from companies.models import CompanyProfile

        return CompanyProfile.objects.get(bidder_id=bidder_id)

    def flag_high_risk(self, bidder_id: int, reason: str) -> None:
        """
        Unconditionally set risk_status = HIGH_RISK for *bidder_id*.

        Called when:
        - win rate > 60 % in a single category over rolling 12 months (Req 7.3)
        - bidder is linked to a CollusionRing (Req 7.4)
        """
        from bids.models import Bidder
        from companies.models import CompanyProfile, RiskStatus

        try:
            bidder = Bidder.objects.get(pk=bidder_id)
        except Bidder.DoesNotExist:
            logger.error("BehavioralTracker.flag_high_risk: Bidder %s not found", bidder_id)
            raise

        profile, _ = CompanyProfile.objects.get_or_create(bidder=bidder)
        profile.risk_status = RiskStatus.HIGH_RISK
        profile.save(update_fields=["risk_status", "updated_at"])

        logger.info(
            "BehavioralTracker: flagged bidder %s as HIGH_RISK — reason: %s",
            bidder_id,
            reason,
        )

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _compute_avg_bid_deviation(self, bids_qs) -> float:
        """
        Mean of |(bid_amount - estimated_value) / estimated_value| across all bids.
        Returns 0.0 when there are no bids or all estimated values are zero.
        """
        deviations = []
        for bid in bids_qs.select_related("tender"):
            est = float(bid.tender.estimated_value)
            if est != 0:
                deviations.append(abs((float(bid.bid_amount) - est) / est))
        return sum(deviations) / len(deviations) if deviations else 0.0

    def _compute_risk_status(self, bidder, overall_win_rate: float, profile) -> str:
        """
        Derive risk_status from win-rate per category over rolling 12 months.

        Returns RiskStatus.HIGH_RISK if any single category exceeds the
        threshold; otherwise returns LOW or MEDIUM based on overall win rate.
        """
        from bids.models import Bid
        from companies.models import RiskStatus

        cutoff = timezone.now() - timedelta(days=self.ROLLING_WINDOW_DAYS)

        # Group wins and total bids by category within the rolling window
        recent_bids = (
            Bid.objects.filter(bidder=bidder, submission_timestamp__gte=cutoff)
            .select_related("tender")
        )

        category_stats: dict[str, dict] = {}
        for bid in recent_bids:
            cat = bid.tender.category
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "wins": 0}
            category_stats[cat]["total"] += 1
            if bid.is_winner:
                category_stats[cat]["wins"] += 1

        for cat, stats in category_stats.items():
            if stats["total"] > 0:
                cat_win_rate = stats["wins"] / stats["total"]
                if cat_win_rate > self.HIGH_RISK_WIN_RATE_THRESHOLD:
                    return RiskStatus.HIGH_RISK

        # Fallback: coarse status from overall win rate
        if overall_win_rate > 0.5:
            return RiskStatus.MEDIUM
        return RiskStatus.LOW
