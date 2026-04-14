"""
Feature engineering for TenderShield ML pipeline.

compute_bid_screens(bids, tender) computes 9 statistical bid-screen features
used as inputs to the Isolation Forest and Random Forest models.

CONTRACT:
  - Returns None when len(bids) < 3 (per Requirement 4.5).
    The caller is responsible for setting ml_anomaly_score = null and
    ml_collusion_score = null when this function returns None.
  - Returns a dict of 9 features when len(bids) >= 3.
  - This function is pure: it makes no database calls. All data is passed in
    as plain Python dicts/lists.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

import numpy as np


def compute_bid_screens(
    bids: list[dict],
    tender: dict,
    bidder_win_rate_in_category: float = 0.0,
) -> Optional[dict]:
    """Compute 9 bid-screen features for a tender.

    Parameters
    ----------
    bids:
        List of bid dicts, each containing at minimum:
          - bid_amount (Decimal or float)
          - is_winner (bool)
          - submission_timestamp (datetime)
          - bidder_id (str)
    tender:
        Tender dict containing at minimum:
          - estimated_value (Decimal or float)
          - submission_deadline (datetime)
          - publication_date (datetime or None)
          - category (str)
          - id (int)
    bidder_win_rate_in_category:
        The winning bidder's historical win rate in this category, looked up
        externally and passed in. Defaults to 0.0.

    Returns
    -------
    dict with keys:
        cv_bids, bid_spread_ratio, norm_winning_distance, single_bidder_flag,
        price_deviation_pct, deadline_days, repeat_winner_rate, bidder_count,
        winner_bid_rank
    or None if len(bids) < 3 (per Requirement 4.5).
    """
    if len(bids) < 3:
        return None

    amounts = np.array([float(b["bid_amount"]) for b in bids], dtype=float)
    mean_amt = float(np.mean(amounts))
    std_amt = float(np.std(amounts, ddof=0))  # population std

    # --- cv_bids: coefficient of variation ---
    cv_bids = (std_amt / mean_amt) if mean_amt != 0.0 else 0.0

    # --- bid_spread_ratio: max / min ---
    min_amt = float(np.min(amounts))
    max_amt = float(np.max(amounts))
    bid_spread_ratio = (max_amt / min_amt) if min_amt != 0.0 else 0.0

    # --- winning bid ---
    winner_bids = [b for b in bids if b.get("is_winner")]
    if winner_bids:
        winning_bid = float(winner_bids[0]["bid_amount"])
    else:
        # No winner marked — use the minimum bid as the proxy winner
        winning_bid = min_amt

    # --- norm_winning_distance: (mean - winning) / std ---
    # Handle std == 0 gracefully (all bids equal)
    norm_winning_distance = (
        (mean_amt - winning_bid) / std_amt if std_amt != 0.0 else 0.0
    )

    # --- single_bidder_flag ---
    single_bidder_flag = 1 if len(bids) == 1 else 0

    # --- price_deviation_pct: (winning - estimated) / estimated ---
    estimated_value = float(tender["estimated_value"])
    price_deviation_pct = (
        (winning_bid - estimated_value) / estimated_value
        if estimated_value != 0.0
        else 0.0
    )

    # --- deadline_days: (submission_deadline - publication_date).days ---
    submission_deadline: datetime = tender["submission_deadline"]
    publication_date: Optional[datetime] = tender.get("publication_date")
    if publication_date is not None:
        deadline_days = (submission_deadline - publication_date).days
    else:
        deadline_days = 0

    # --- repeat_winner_rate: pass-through ---
    repeat_winner_rate = float(bidder_win_rate_in_category)

    # --- bidder_count ---
    bidder_count = len(bids)

    # --- winner_bid_rank: rank of winning bid (ascending, 1 = lowest) ---
    sorted_amounts = sorted(float(b["bid_amount"]) for b in bids)
    # Find the 1-based rank of the winning bid (first occurrence)
    winner_bid_rank = sorted_amounts.index(winning_bid) + 1

    return {
        "cv_bids": cv_bids,
        "bid_spread_ratio": bid_spread_ratio,
        "norm_winning_distance": norm_winning_distance,
        "single_bidder_flag": single_bidder_flag,
        "price_deviation_pct": price_deviation_pct,
        "deadline_days": deadline_days,
        "repeat_winner_rate": repeat_winner_rate,
        "bidder_count": bidder_count,
        "winner_bid_rank": winner_bid_rank,
    }
