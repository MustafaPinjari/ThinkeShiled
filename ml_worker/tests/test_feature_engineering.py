"""
Unit tests for ml_worker/services/feature_engineering.py

All tests use plain Python dicts — no database connection required.
"""

import math
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from ml_worker.services.feature_engineering import compute_bid_screens


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_bid(bid_amount, is_winner=False, bidder_id="b1"):
    return {
        "bid_amount": Decimal(str(bid_amount)),
        "is_winner": is_winner,
        "submission_timestamp": datetime(2024, 1, 10, tzinfo=timezone.utc),
        "bidder_id": bidder_id,
    }


def make_tender(
    estimated_value=100.0,
    submission_deadline=None,
    publication_date=None,
    category="IT",
    tender_id=1,
):
    if submission_deadline is None:
        submission_deadline = datetime(2024, 2, 1, tzinfo=timezone.utc)
    return {
        "estimated_value": Decimal(str(estimated_value)),
        "submission_deadline": submission_deadline,
        "publication_date": publication_date,
        "category": category,
        "id": tender_id,
    }


# ---------------------------------------------------------------------------
# 1. Null return for < 3 bids
# ---------------------------------------------------------------------------

class TestNullReturnForFewBids:
    def test_zero_bids_returns_none(self):
        assert compute_bid_screens([], make_tender()) is None

    def test_one_bid_returns_none(self):
        bids = [make_bid(100, is_winner=True)]
        assert compute_bid_screens(bids, make_tender()) is None

    def test_two_bids_returns_none(self):
        bids = [make_bid(100, is_winner=True), make_bid(120)]
        assert compute_bid_screens(bids, make_tender()) is None

    def test_exactly_three_bids_returns_dict(self):
        bids = [make_bid(100, is_winner=True), make_bid(120), make_bid(140)]
        result = compute_bid_screens(bids, make_tender())
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 2. Basic computation — verify all 9 keys are present
# ---------------------------------------------------------------------------

class TestBasicComputation:
    def setup_method(self):
        self.bids = [
            make_bid(80, is_winner=True, bidder_id="b1"),
            make_bid(100, bidder_id="b2"),
            make_bid(120, bidder_id="b3"),
        ]
        self.tender = make_tender(
            estimated_value=100.0,
            submission_deadline=datetime(2024, 2, 1, tzinfo=timezone.utc),
            publication_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        )
        self.result = compute_bid_screens(self.bids, self.tender)

    def test_returns_dict(self):
        assert isinstance(self.result, dict)

    def test_all_keys_present(self):
        expected_keys = {
            "cv_bids", "bid_spread_ratio", "norm_winning_distance",
            "single_bidder_flag", "price_deviation_pct", "deadline_days",
            "repeat_winner_rate", "bidder_count", "winner_bid_rank",
        }
        assert set(self.result.keys()) == expected_keys


# ---------------------------------------------------------------------------
# 3. cv_bids
# ---------------------------------------------------------------------------

class TestCvBids:
    def test_known_cv(self):
        # amounts: 80, 100, 120 → mean=100, std=16.329..., cv=0.16329...
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        import numpy as np
        amounts = [80.0, 100.0, 120.0]
        expected = np.std(amounts) / np.mean(amounts)
        assert math.isclose(result["cv_bids"], expected, rel_tol=1e-9)

    def test_cv_all_equal_is_zero(self):
        bids = [make_bid(100, is_winner=True), make_bid(100), make_bid(100)]
        result = compute_bid_screens(bids, make_tender())
        assert result["cv_bids"] == 0.0


# ---------------------------------------------------------------------------
# 4. bid_spread_ratio
# ---------------------------------------------------------------------------

class TestBidSpreadRatio:
    def test_known_ratio(self):
        # max=120, min=80 → ratio=1.5
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert math.isclose(result["bid_spread_ratio"], 120.0 / 80.0, rel_tol=1e-9)

    def test_all_equal_ratio_is_one(self):
        bids = [make_bid(100, is_winner=True), make_bid(100), make_bid(100)]
        result = compute_bid_screens(bids, make_tender())
        assert math.isclose(result["bid_spread_ratio"], 1.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 5. norm_winning_distance
# ---------------------------------------------------------------------------

class TestNormWinningDistance:
    def test_winner_below_mean_is_positive(self):
        # amounts: 80(W), 100, 120 → mean=100, std≈16.33, winner=80
        # norm = (100 - 80) / 16.33 > 0
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert result["norm_winning_distance"] > 0

    def test_winner_above_mean_is_negative(self):
        # amounts: 80, 100, 120(W) → mean=100, winner=120
        # norm = (100 - 120) / std < 0
        bids = [make_bid(80), make_bid(100), make_bid(120, is_winner=True)]
        result = compute_bid_screens(bids, make_tender())
        assert result["norm_winning_distance"] < 0

    def test_winner_at_mean_is_zero(self):
        # amounts: 80, 100(W), 120 → mean=100, winner=100
        bids = [make_bid(80), make_bid(100, is_winner=True), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert math.isclose(result["norm_winning_distance"], 0.0, abs_tol=1e-9)

    def test_all_equal_std_zero_returns_zero(self):
        bids = [make_bid(100, is_winner=True), make_bid(100), make_bid(100)]
        result = compute_bid_screens(bids, make_tender())
        assert result["norm_winning_distance"] == 0.0


# ---------------------------------------------------------------------------
# 6. single_bidder_flag
# ---------------------------------------------------------------------------

class TestSingleBidderFlag:
    def test_three_bids_flag_is_zero(self):
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert result["single_bidder_flag"] == 0

    def test_many_bids_flag_is_zero(self):
        bids = [make_bid(i, is_winner=(i == 80)) for i in [80, 90, 100, 110]]
        result = compute_bid_screens(bids, make_tender())
        assert result["single_bidder_flag"] == 0

    # Note: single_bidder_flag == 1 only when len(bids) == 1, which triggers
    # the None return guard. So we verify the formula is correct for len >= 3.
    def test_flag_formula_for_three_bids(self):
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert result["single_bidder_flag"] == (1 if len(bids) == 1 else 0)


# ---------------------------------------------------------------------------
# 7. price_deviation_pct
# ---------------------------------------------------------------------------

class TestPriceDeviationPct:
    def test_winning_bid_above_estimated(self):
        # winner=120, estimated=100 → (120-100)/100 = 0.2
        bids = [make_bid(80), make_bid(100), make_bid(120, is_winner=True)]
        result = compute_bid_screens(bids, make_tender(estimated_value=100.0))
        assert math.isclose(result["price_deviation_pct"], 0.2, rel_tol=1e-9)

    def test_winning_bid_below_estimated(self):
        # winner=80, estimated=100 → (80-100)/100 = -0.2
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender(estimated_value=100.0))
        assert math.isclose(result["price_deviation_pct"], -0.2, rel_tol=1e-9)

    def test_winning_bid_equals_estimated(self):
        bids = [make_bid(100, is_winner=True), make_bid(110), make_bid(120)]
        result = compute_bid_screens(bids, make_tender(estimated_value=100.0))
        assert math.isclose(result["price_deviation_pct"], 0.0, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# 8. deadline_days
# ---------------------------------------------------------------------------

class TestDeadlineDays:
    def test_known_date_difference(self):
        pub = datetime(2024, 1, 1, tzinfo=timezone.utc)
        deadline = datetime(2024, 2, 1, tzinfo=timezone.utc)
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        tender = make_tender(submission_deadline=deadline, publication_date=pub)
        result = compute_bid_screens(bids, tender)
        assert result["deadline_days"] == 31

    def test_none_publication_date_returns_zero(self):
        deadline = datetime(2024, 2, 1, tzinfo=timezone.utc)
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        tender = make_tender(submission_deadline=deadline, publication_date=None)
        result = compute_bid_screens(bids, tender)
        assert result["deadline_days"] == 0


# ---------------------------------------------------------------------------
# 9. bidder_count
# ---------------------------------------------------------------------------

class TestBidderCount:
    def test_three_bids(self):
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert result["bidder_count"] == 3

    def test_five_bids(self):
        bids = [make_bid(i, is_winner=(i == 80)) for i in [80, 90, 100, 110, 120]]
        result = compute_bid_screens(bids, make_tender())
        assert result["bidder_count"] == 5


# ---------------------------------------------------------------------------
# 10. winner_bid_rank
# ---------------------------------------------------------------------------

class TestWinnerBidRank:
    def test_winner_is_lowest_bid_rank_1(self):
        # sorted: [80, 100, 120] → winner=80 → rank 1
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert result["winner_bid_rank"] == 1

    def test_winner_is_highest_bid_rank_n(self):
        # sorted: [80, 100, 120] → winner=120 → rank 3
        bids = [make_bid(80), make_bid(100), make_bid(120, is_winner=True)]
        result = compute_bid_screens(bids, make_tender())
        assert result["winner_bid_rank"] == 3

    def test_winner_is_middle_bid(self):
        # sorted: [80, 100, 120] → winner=100 → rank 2
        bids = [make_bid(80), make_bid(100, is_winner=True), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert result["winner_bid_rank"] == 2

    def test_no_winner_marked_uses_min_bid(self):
        # No winner → proxy = min = 80 → rank 1
        bids = [make_bid(80), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert result["winner_bid_rank"] == 1


# ---------------------------------------------------------------------------
# 11. repeat_winner_rate pass-through
# ---------------------------------------------------------------------------

class TestRepeatWinnerRate:
    def test_default_is_zero(self):
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender())
        assert result["repeat_winner_rate"] == 0.0

    def test_custom_rate_passed_through(self):
        bids = [make_bid(80, is_winner=True), make_bid(100), make_bid(120)]
        result = compute_bid_screens(bids, make_tender(), bidder_win_rate_in_category=0.75)
        assert math.isclose(result["repeat_winner_rate"], 0.75, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# 12. Edge case: all bids equal
# ---------------------------------------------------------------------------

class TestAllBidsEqual:
    def setup_method(self):
        self.bids = [
            make_bid(100, is_winner=True),
            make_bid(100),
            make_bid(100),
        ]
        self.result = compute_bid_screens(self.bids, make_tender(estimated_value=100.0))

    def test_cv_bids_is_zero(self):
        assert self.result["cv_bids"] == 0.0

    def test_bid_spread_ratio_is_one(self):
        assert math.isclose(self.result["bid_spread_ratio"], 1.0, rel_tol=1e-9)

    def test_norm_winning_distance_is_zero(self):
        assert self.result["norm_winning_distance"] == 0.0

    def test_no_exception_raised(self):
        # Verifies division-by-zero is handled gracefully
        assert self.result is not None
