# Feature: tender-shield, Property 13: Company Profile Metrics Correctness
# Feature: tender-shield, Property 14: HIGH_RISK Status Invariant
#
# Property 13: For any set of bid and award records for a bidder, the computed
# profile metrics match the values derived by applying the metric formulas to
# the underlying records.
# Validates: Requirements 7.2
#
# Property 14: For any bidder whose win rate in a single category exceeds 60%
# over 12 months, or who is linked to a CollusionRing, risk_status is HIGH_RISK;
# a bidder not meeting either condition must not have HIGH_RISK set by these rules.
# Validates: Requirements 7.3, 7.4

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import List

from django.utils import timezone
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

from bids.models import Bid, Bidder
from companies.models import CompanyProfile, RiskStatus
from companies.tracker import BehavioralTracker
from graph.models import CollusionRing
from tenders.models import Tender


# ---------------------------------------------------------------------------
# Dataclasses used as strategy targets
# ---------------------------------------------------------------------------

@dataclass
class BidRecord:
    """Represents a single bid by a bidder on a tender."""
    bid_amount: float          # absolute amount
    estimated_value: float     # tender's estimated value (> 0)
    is_winner: bool
    category: str
    days_ago: int              # how many days ago the bid was submitted


@dataclass
class CompanyHistory:
    """Compact representation of a bidder's history for Property 14."""
    # Per-category win rates within the rolling 12-month window
    # Each entry: (category, total_bids_in_window, wins_in_window)
    category_stats: List[tuple]   # [(cat, total, wins), ...]
    in_ring: bool                 # whether bidder is linked to a CollusionRing


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_category_st = st.sampled_from(["IT", "Construction", "Roads", "Healthcare", "Education"])

_bid_record_st = st.builds(
    BidRecord,
    bid_amount=st.floats(min_value=1_000.0, max_value=10_000_000.0,
                         allow_nan=False, allow_infinity=False),
    estimated_value=st.floats(min_value=1_000.0, max_value=10_000_000.0,
                              allow_nan=False, allow_infinity=False),
    is_winner=st.booleans(),
    category=_category_st,
    days_ago=st.integers(min_value=0, max_value=400),
)

# A list of 0–20 bid records for a single bidder
_bid_list_st = st.lists(_bid_record_st, min_size=0, max_size=20)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

_counter = 0


def _uid(prefix: str) -> str:
    global _counter
    _counter += 1
    return f"{prefix}-PBT-{_counter}"


def _make_tender(category: str, estimated_value: float) -> Tender:
    return Tender.objects.create(
        tender_id=_uid("T"),
        title="PBT Tender",
        category=category,
        estimated_value=Decimal(str(round(estimated_value, 2))),
        currency="INR",
        submission_deadline=timezone.now() + timedelta(days=30),
        buyer_id="PBT-BUYER",
        buyer_name="PBT Buyer",
    )


def _make_bidder() -> Bidder:
    return Bidder.objects.create(
        bidder_id=_uid("BIDDER"),
        bidder_name="PBT Corp",
    )


def _make_bid(bidder: Bidder, tender: Tender, bid_amount: float,
              is_winner: bool, days_ago: int) -> Bid:
    return Bid.objects.create(
        bid_id=_uid("BID"),
        tender=tender,
        bidder=bidder,
        bid_amount=Decimal(str(round(bid_amount, 2))),
        submission_timestamp=timezone.now() - timedelta(days=days_ago),
        is_winner=is_winner,
    )


# ---------------------------------------------------------------------------
# Reference implementations of the metric formulas
# ---------------------------------------------------------------------------

def _ref_total_bids(records: List[BidRecord]) -> int:
    return len(records)


def _ref_total_wins(records: List[BidRecord]) -> int:
    return sum(1 for r in records if r.is_winner)


def _ref_win_rate(records: List[BidRecord]) -> float:
    total = len(records)
    if total == 0:
        return 0.0
    return round(_ref_total_wins(records) / total, 4)


def _ref_avg_bid_deviation(records: List[BidRecord]) -> float:
    """Mean of |bid_amount - estimated_value| / estimated_value."""
    deviations = [
        abs((r.bid_amount - r.estimated_value) / r.estimated_value)
        for r in records
        if r.estimated_value != 0
    ]
    if not deviations:
        return 0.0
    return round(sum(deviations) / len(deviations), 4)


def _ref_category_win_rate_exceeds_threshold(
    records: List[BidRecord],
    threshold: float = 0.60,
    window_days: int = 365,
) -> bool:
    """
    Returns True if any single category has a win rate > threshold
    within the rolling window_days window.
    """
    from collections import defaultdict
    stats: dict = defaultdict(lambda: {"total": 0, "wins": 0})
    for r in records:
        if r.days_ago <= window_days:
            stats[r.category]["total"] += 1
            if r.is_winner:
                stats[r.category]["wins"] += 1
    for cat, s in stats.items():
        if s["total"] > 0 and (s["wins"] / s["total"]) > threshold:
            return True
    return False


# ===========================================================================
# Property 13 — Company Profile Metrics Correctness
# ===========================================================================

class CompanyProfileMetricsPropertyTest(TestCase):
    """
    Property 13: For any set of bid and award records for a bidder, the
    computed profile metrics match the values derived by applying the metric
    formulas to the underlying records.
    Validates: Requirements 7.2
    """

    @given(_bid_list_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_total_bids_matches_record_count(self, records: List[BidRecord]):
        # Feature: tender-shield, Property 13: Company Profile Metrics Correctness
        bidder = _make_bidder()
        for r in records:
            tender = _make_tender(r.category, r.estimated_value)
            _make_bid(bidder, tender, r.bid_amount, r.is_winner, r.days_ago)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        expected = _ref_total_bids(records)
        assert profile.total_bids == expected, (
            f"total_bids mismatch: got {profile.total_bids}, expected {expected}"
        )

    @given(_bid_list_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_total_wins_matches_winner_count(self, records: List[BidRecord]):
        # Feature: tender-shield, Property 13: Company Profile Metrics Correctness
        bidder = _make_bidder()
        for r in records:
            tender = _make_tender(r.category, r.estimated_value)
            _make_bid(bidder, tender, r.bid_amount, r.is_winner, r.days_ago)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        expected = _ref_total_wins(records)
        assert profile.total_wins == expected, (
            f"total_wins mismatch: got {profile.total_wins}, expected {expected}"
        )

    @given(_bid_list_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_win_rate_equals_wins_over_total(self, records: List[BidRecord]):
        # Feature: tender-shield, Property 13: Company Profile Metrics Correctness
        bidder = _make_bidder()
        for r in records:
            tender = _make_tender(r.category, r.estimated_value)
            _make_bid(bidder, tender, r.bid_amount, r.is_winner, r.days_ago)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        expected = _ref_win_rate(records)
        assert abs(float(profile.win_rate) - expected) < 1e-3, (
            f"win_rate mismatch: got {profile.win_rate}, expected {expected} "
            f"(records={len(records)}, wins={_ref_total_wins(records)})"
        )

    @given(_bid_list_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_avg_bid_deviation_matches_formula(self, records: List[BidRecord]):
        # Feature: tender-shield, Property 13: Company Profile Metrics Correctness
        bidder = _make_bidder()
        for r in records:
            tender = _make_tender(r.category, r.estimated_value)
            _make_bid(bidder, tender, r.bid_amount, r.is_winner, r.days_ago)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        expected = _ref_avg_bid_deviation(records)
        assert abs(float(profile.avg_bid_deviation) - expected) < 1e-3, (
            f"avg_bid_deviation mismatch: got {profile.avg_bid_deviation}, "
            f"expected {expected}"
        )

    @given(st.just([]))
    @settings(max_examples=10, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_win_rate_zero_when_no_bids(self, records: List[BidRecord]):
        # Feature: tender-shield, Property 13: Company Profile Metrics Correctness
        # When there are no bids, win_rate must be 0.0
        bidder = _make_bidder()

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        assert float(profile.win_rate) == 0.0, (
            f"win_rate should be 0.0 with no bids, got {profile.win_rate}"
        )

    @given(_bid_list_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_win_rate_bounded_in_zero_one(self, records: List[BidRecord]):
        # Feature: tender-shield, Property 13: Company Profile Metrics Correctness
        bidder = _make_bidder()
        for r in records:
            tender = _make_tender(r.category, r.estimated_value)
            _make_bid(bidder, tender, r.bid_amount, r.is_winner, r.days_ago)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        assert 0.0 <= float(profile.win_rate) <= 1.0, (
            f"win_rate {profile.win_rate} is outside [0, 1]"
        )

    @given(_bid_list_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_total_wins_never_exceeds_total_bids(self, records: List[BidRecord]):
        # Feature: tender-shield, Property 13: Company Profile Metrics Correctness
        bidder = _make_bidder()
        for r in records:
            tender = _make_tender(r.category, r.estimated_value)
            _make_bid(bidder, tender, r.bid_amount, r.is_winner, r.days_ago)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        assert profile.total_wins <= profile.total_bids, (
            f"total_wins ({profile.total_wins}) exceeds total_bids ({profile.total_bids})"
        )

    @given(_bid_list_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_avg_bid_deviation_non_negative(self, records: List[BidRecord]):
        # Feature: tender-shield, Property 13: Company Profile Metrics Correctness
        bidder = _make_bidder()
        for r in records:
            tender = _make_tender(r.category, r.estimated_value)
            _make_bid(bidder, tender, r.bid_amount, r.is_winner, r.days_ago)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        assert float(profile.avg_bid_deviation) >= 0.0, (
            f"avg_bid_deviation {profile.avg_bid_deviation} is negative"
        )


# ===========================================================================
# Property 14 — HIGH_RISK Status Invariant
# ===========================================================================

class HighRiskStatusInvariantPropertyTest(TestCase):
    """
    Property 14: For any bidder whose win rate in a single category exceeds
    60% over 12 months, or who is linked to a CollusionRing, risk_status is
    HIGH_RISK; a bidder not meeting either condition must not have HIGH_RISK
    set by these rules.
    Validates: Requirements 7.3, 7.4
    """

    @given(
        win_rate=st.floats(min_value=0.0, max_value=1.0,
                           allow_nan=False, allow_infinity=False),
        in_ring=st.booleans(),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_high_risk_when_category_win_rate_exceeds_threshold(
        self, win_rate: float, in_ring: bool
    ):
        # Feature: tender-shield, Property 14: HIGH_RISK Status Invariant
        #
        # When win_rate > 0.60 in a single category within 12 months,
        # risk_status MUST be HIGH_RISK regardless of in_ring.
        assume(win_rate > BehavioralTracker.HIGH_RISK_WIN_RATE_THRESHOLD)

        bidder = _make_bidder()
        category = "IT"

        # Build exactly 10 bids in the same category within the rolling window,
        # with the requested win rate (rounded to nearest integer wins).
        total = 10
        wins = max(1, round(win_rate * total))
        # Ensure wins/total actually exceeds the threshold
        assume(wins / total > BehavioralTracker.HIGH_RISK_WIN_RATE_THRESHOLD)

        for i in range(total):
            tender = _make_tender(category, 100_000.0)
            _make_bid(bidder, tender, 90_000.0, is_winner=(i < wins), days_ago=30)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        assert profile.risk_status == RiskStatus.HIGH_RISK, (
            f"Expected HIGH_RISK for win_rate={wins}/{total}="
            f"{wins/total:.4f} > {BehavioralTracker.HIGH_RISK_WIN_RATE_THRESHOLD}, "
            f"got {profile.risk_status}"
        )

    @given(
        win_rate=st.floats(min_value=0.0, max_value=0.60,
                           allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_not_high_risk_when_win_rate_at_or_below_threshold(self, win_rate: float):
        # Feature: tender-shield, Property 14: HIGH_RISK Status Invariant
        #
        # When win_rate <= 0.60 in all categories and bidder is NOT in a ring,
        # risk_status must NOT be HIGH_RISK (from these rules alone).
        assume(win_rate <= BehavioralTracker.HIGH_RISK_WIN_RATE_THRESHOLD)

        bidder = _make_bidder()
        category = "IT"

        # Build 10 bids where wins/10 <= 0.60 (i.e., wins <= 6)
        total = 10
        wins = min(6, round(win_rate * total))
        # Confirm wins/total does not exceed threshold
        assume(wins / total <= BehavioralTracker.HIGH_RISK_WIN_RATE_THRESHOLD)

        for i in range(total):
            tender = _make_tender(category, 100_000.0)
            _make_bid(bidder, tender, 90_000.0, is_winner=(i < wins), days_ago=30)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        assert profile.risk_status != RiskStatus.HIGH_RISK, (
            f"Expected NOT HIGH_RISK for win_rate={wins}/{total}="
            f"{wins/total:.4f} <= {BehavioralTracker.HIGH_RISK_WIN_RATE_THRESHOLD}, "
            f"got {profile.risk_status}"
        )

    @given(in_ring=st.booleans())
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_high_risk_when_linked_to_collusion_ring(self, in_ring: bool):
        # Feature: tender-shield, Property 14: HIGH_RISK Status Invariant
        #
        # When a bidder is linked to a CollusionRing, flag_high_risk() must
        # set risk_status = HIGH_RISK.
        bidder = _make_bidder()

        # Create a low-risk profile first (no bids, no ring)
        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)
        assert profile.risk_status != RiskStatus.HIGH_RISK

        if in_ring:
            ring = CollusionRing.objects.create(
                ring_id=_uid("RING"),
                member_bidder_ids=[bidder.pk],
                member_count=3,
            )
            profile.collusion_ring = ring
            profile.save(update_fields=["collusion_ring", "updated_at"])

            tracker.flag_high_risk(bidder.pk, reason=f"CollusionRing {ring.ring_id}")
            profile.refresh_from_db()

            assert profile.risk_status == RiskStatus.HIGH_RISK, (
                f"Expected HIGH_RISK when linked to CollusionRing, "
                f"got {profile.risk_status}"
            )
        else:
            # Not in a ring and no high win rate → must NOT be HIGH_RISK
            profile.refresh_from_db()
            assert profile.risk_status != RiskStatus.HIGH_RISK, (
                f"Expected NOT HIGH_RISK when not in ring and no high win rate, "
                f"got {profile.risk_status}"
            )

    @given(
        win_rate=st.floats(min_value=0.0, max_value=1.0,
                           allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_wins_outside_rolling_window_do_not_trigger_high_risk(self, win_rate: float):
        # Feature: tender-shield, Property 14: HIGH_RISK Status Invariant
        #
        # Wins older than 365 days must not count toward the HIGH_RISK threshold.
        assume(win_rate > BehavioralTracker.HIGH_RISK_WIN_RATE_THRESHOLD)

        bidder = _make_bidder()
        category = "Roads"

        total = 10
        wins = max(1, round(win_rate * total))
        assume(wins / total > BehavioralTracker.HIGH_RISK_WIN_RATE_THRESHOLD)

        # All bids placed 400 days ago — outside the 365-day rolling window
        for i in range(total):
            tender = _make_tender(category, 100_000.0)
            _make_bid(bidder, tender, 90_000.0, is_winner=(i < wins), days_ago=400)

        tracker = BehavioralTracker()
        profile = tracker.update_profile(bidder.pk)

        assert profile.risk_status != RiskStatus.HIGH_RISK, (
            f"Wins outside rolling window should not trigger HIGH_RISK, "
            f"got {profile.risk_status} (win_rate={wins}/{total})"
        )

    @given(_bid_list_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_high_risk_once_set_is_not_downgraded_by_update_profile(
        self, records: List[BidRecord]
    ):
        # Feature: tender-shield, Property 14: HIGH_RISK Status Invariant
        #
        # Once HIGH_RISK is set via flag_high_risk(), update_profile() must
        # never downgrade the status.
        bidder = _make_bidder()

        tracker = BehavioralTracker()
        # Set HIGH_RISK first
        tracker.update_profile(bidder.pk)
        tracker.flag_high_risk(bidder.pk, reason="test invariant")

        # Now add arbitrary bids and recompute
        for r in records:
            tender = _make_tender(r.category, r.estimated_value)
            _make_bid(bidder, tender, r.bid_amount, r.is_winner, r.days_ago)

        profile = tracker.update_profile(bidder.pk)

        assert profile.risk_status == RiskStatus.HIGH_RISK, (
            f"HIGH_RISK must not be downgraded by update_profile(), "
            f"got {profile.risk_status}"
        )
