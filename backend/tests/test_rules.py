# Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly
#
# For any tender satisfying a rule trigger condition, the corresponding
# RedFlag is raised with the correct type and severity; for any tender not
# satisfying the condition, the flag is not raised. Covers all 6 rules.
# Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.utils import timezone
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

from bids.models import Bid, Bidder
from detection.engine import FraudDetectionEngine
from detection.models import FlagType, RuleDefinition, Severity
from tenders.models import Tender

# ---------------------------------------------------------------------------
# Helpers (mirrors detection/tests.py helpers, kept local for isolation)
# ---------------------------------------------------------------------------

_tender_counter = 0
_bidder_counter = 0
_bid_counter = 0


def _make_tender(category="IT", estimated_value="100000.00", days_offset=10,
                 publication_date=None, **kwargs):
    global _tender_counter
    _tender_counter += 1
    now = timezone.now()
    pub = publication_date or (now - timedelta(days=1))
    return Tender.objects.create(
        tender_id=f"PBT-T-{_tender_counter}",
        title="PBT Tender",
        category=category,
        estimated_value=Decimal(estimated_value),
        currency="INR",
        submission_deadline=now + timedelta(days=days_offset),
        buyer_id="PBT-BUYER",
        buyer_name="PBT Buyer",
        publication_date=pub,
        created_at=pub,
        **kwargs,
    )


def _make_bidder(address="Unique St", directors="Director A"):
    global _bidder_counter
    _bidder_counter += 1
    return Bidder.objects.create(
        bidder_id=f"PBT-B-{_bidder_counter}",
        bidder_name=f"PBT Bidder {_bidder_counter}",
        registered_address=address,
        director_names=directors,
    )


def _make_bid(tender, bidder, amount="90000.00", timestamp=None):
    global _bid_counter
    _bid_counter += 1
    return Bid.objects.create(
        bid_id=f"PBT-BID-{_bid_counter}",
        tender=tender,
        bidder=bidder,
        bid_amount=Decimal(amount),
        submission_timestamp=timestamp or timezone.now(),
    )


def _setup_rules():
    """Ensure all 6 default rules exist."""
    def _get_or_create(code, severity, params):
        RuleDefinition.objects.get_or_create(
            rule_code=code,
            defaults={
                "description": f"PBT rule {code}",
                "severity": severity,
                "is_active": True,
                "parameters": params,
            },
        )

    _get_or_create(FlagType.SINGLE_BIDDER, Severity.HIGH, {})
    _get_or_create(FlagType.PRICE_ANOMALY, Severity.MEDIUM, {"threshold": "0.40"})
    _get_or_create(FlagType.REPEAT_WINNER, Severity.HIGH, {"threshold": 0.60})
    _get_or_create(FlagType.SHORT_DEADLINE, Severity.MEDIUM, {"min_days": 3})
    _get_or_create(FlagType.LINKED_ENTITIES, Severity.HIGH, {})
    _get_or_create(FlagType.COVER_BID_PATTERN, Severity.HIGH, {"window_days": 30, "min_bids": 3})


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Bid count strategies
_st_single_bidder_count = st.just(1)
_st_multi_bidder_count = st.integers(min_value=2, max_value=6)

# Price deviation strategies (as a fraction of estimated_value)
# Trigger: deviation > 0.40 in either direction
_st_triggering_deviation = st.one_of(
    st.floats(min_value=0.401, max_value=2.0, allow_nan=False, allow_infinity=False),
    st.floats(min_value=-0.999, max_value=-0.401, allow_nan=False, allow_infinity=False),
)
_st_safe_deviation = st.floats(
    min_value=-0.399, max_value=0.399, allow_nan=False, allow_infinity=False
)

# Deadline delta strategies (seconds from publication)
# Trigger: delta < 3 * 86400
_st_short_delta = st.integers(min_value=1, max_value=3 * 86400 - 1)
_st_long_delta = st.integers(min_value=3 * 86400, max_value=30 * 86400)

# Win-rate strategies (wins, total) where wins/total > 0.60
_st_triggering_win_rate = st.integers(min_value=2, max_value=10).flatmap(
    lambda total: st.integers(
        min_value=int(total * 0.60) + 1, max_value=total
    ).map(lambda wins: (wins, total))
)
_st_safe_win_rate = st.integers(min_value=2, max_value=10).flatmap(
    lambda total: st.integers(
        min_value=0, max_value=int(total * 0.60)
    ).map(lambda wins: (wins, total))
)

# Cover-bid count strategies
_st_triggering_cover_count = st.integers(min_value=3, max_value=8)
_st_safe_cover_count = st.integers(min_value=1, max_value=2)

# Shared link type
_st_link_type = st.sampled_from(["address", "director"])


# ---------------------------------------------------------------------------
# Property 7a — SINGLE_BIDDER
# ---------------------------------------------------------------------------

class SingleBidderPBTTest(TestCase):
    """
    Property 7 (SINGLE_BIDDER): For any tender with exactly 1 bidder,
    SINGLE_BIDDER (HIGH) is raised. For any tender with ≥2 bidders,
    SINGLE_BIDDER is not raised.
    Validates: Requirement 3.1
    """

    def setUp(self):
        _setup_rules()
        self.engine = FraudDetectionEngine()

    @given(_st_single_bidder_count)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_single_bidder_raises_flag(self, _count):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (SINGLE_BIDDER trigger)
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            bidder = _make_bidder()
            _make_bid(tender, bidder)

            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.SINGLE_BIDDER in flag_types, (
            "Expected SINGLE_BIDDER flag for tender with 1 bidder"
        )
        sb_flags = [f for f in flags if f.flag_type == FlagType.SINGLE_BIDDER]
        assert sb_flags[0].severity == Severity.HIGH, (
            f"Expected HIGH severity, got {sb_flags[0].severity}"
        )

    @given(_st_multi_bidder_count)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_multiple_bidders_no_flag(self, bidder_count):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (SINGLE_BIDDER no-trigger)
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            for i in range(bidder_count):
                bidder = _make_bidder(
                    address=f"Distinct Addr {tender.pk}-{i}",
                    directors=f"Director {tender.pk}-{i}",
                )
                _make_bid(tender, bidder, str(90000 + i * 1000))

            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.SINGLE_BIDDER not in flag_types, (
            f"Expected no SINGLE_BIDDER flag for tender with {bidder_count} bidders"
        )


# ---------------------------------------------------------------------------
# Property 7b — PRICE_ANOMALY
# ---------------------------------------------------------------------------

class PriceAnomalyPBTTest(TestCase):
    """
    Property 7 (PRICE_ANOMALY): For any winning bid deviating >40% from
    estimated_value, PRICE_ANOMALY (MEDIUM) is raised. For deviation ≤40%,
    it is not raised.
    Validates: Requirement 3.2
    """

    def setUp(self):
        _setup_rules()
        self.engine = FraudDetectionEngine()

    @given(_st_triggering_deviation)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_triggering_deviation_raises_flag(self, deviation):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (PRICE_ANOMALY trigger)
        estimated = Decimal("100000.00")
        winning_bid = estimated * Decimal(str(1 + deviation))
        assume(winning_bid > Decimal("0.01"))

        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender(estimated_value=str(estimated))
            bidder = _make_bidder()
            _make_bid(tender, bidder, str(winning_bid.quantize(Decimal("0.01"))))

            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.PRICE_ANOMALY in flag_types, (
            f"Expected PRICE_ANOMALY for deviation={deviation:.4f} "
            f"(estimated={estimated}, winning={winning_bid:.2f})"
        )
        pa_flags = [f for f in flags if f.flag_type == FlagType.PRICE_ANOMALY]
        assert pa_flags[0].severity == Severity.MEDIUM, (
            f"Expected MEDIUM severity, got {pa_flags[0].severity}"
        )

    @given(_st_safe_deviation)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_safe_deviation_no_flag(self, deviation):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (PRICE_ANOMALY no-trigger)
        estimated = Decimal("100000.00")
        winning_bid = estimated * Decimal(str(1 + deviation))
        assume(winning_bid > Decimal("0.01"))

        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender(estimated_value=str(estimated))
            bidder = _make_bidder()
            _make_bid(tender, bidder, str(winning_bid.quantize(Decimal("0.01"))))

            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.PRICE_ANOMALY not in flag_types, (
            f"Expected no PRICE_ANOMALY for deviation={deviation:.4f} "
            f"(estimated={estimated}, winning={winning_bid:.2f})"
        )


# ---------------------------------------------------------------------------
# Property 7c — REPEAT_WINNER
# ---------------------------------------------------------------------------

class RepeatWinnerPBTTest(TestCase):
    """
    Property 7 (REPEAT_WINNER): For any bidder winning >60% of tenders in a
    category within 12 months, REPEAT_WINNER (HIGH) is raised. For ≤60%,
    it is not raised.
    Validates: Requirement 3.3
    """

    def setUp(self):
        _setup_rules()
        self.engine = FraudDetectionEngine()

    def _build_scenario(self, wins, total, category):
        """Create `total` tenders; the focus bidder wins `wins` of them."""
        focus = _make_bidder(
            address=f"RW-Focus-{wins}-{total}",
            directors=f"RW-Dir-{wins}-{total}",
        )
        other = _make_bidder(
            address=f"RW-Other-{wins}-{total}",
            directors=f"RW-ODir-{wins}-{total}",
        )
        tenders = []
        for i in range(total):
            t = _make_tender(category=category)
            tenders.append(t)
            if i < wins:
                _make_bid(t, focus, "80000")
                _make_bid(t, other, "90000")
            else:
                _make_bid(t, other, "80000")
                _make_bid(t, focus, "90000")
        return tenders[-1]

    @given(_st_triggering_win_rate)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_above_60_percent_raises_flag(self, win_rate_pair):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (REPEAT_WINNER trigger)
        wins, total = win_rate_pair
        assume(wins / total > 0.60)
        category = f"CAT-RW-{wins}-{total}"

        with patch("bids.tasks.compute_score_task.delay"):
            tender = self._build_scenario(wins, total, category)
            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.REPEAT_WINNER in flag_types, (
            f"Expected REPEAT_WINNER for win_rate={wins}/{total}={wins/total:.3f}"
        )
        rw_flags = [f for f in flags if f.flag_type == FlagType.REPEAT_WINNER]
        assert rw_flags[0].severity == Severity.HIGH, (
            f"Expected HIGH severity, got {rw_flags[0].severity}"
        )

    @given(_st_safe_win_rate)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_at_or_below_60_percent_no_flag(self, win_rate_pair):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (REPEAT_WINNER no-trigger)
        wins, total = win_rate_pair
        assume(wins / total <= 0.60)
        # Use a unique category per example so other tests don't pollute the window
        category = f"CAT-RW-SAFE-{wins}-{total}-{id(win_rate_pair)}"

        with patch("bids.tasks.compute_score_task.delay"):
            tender = self._build_scenario(wins, total, category)
            flags = self.engine.evaluate_rules(tender.pk)

        # The focus bidder (wins/total ≤ 60%) must NOT have a REPEAT_WINNER flag.
        # The "other" bidder may legitimately trigger the flag if their rate > 60%,
        # so we check per-bidder rather than asserting the flag is absent entirely.
        focus_bidder_ids = set(
            Bid.objects.filter(tender=tender, bid_amount=Decimal("90000"))
            .values_list("bidder_id", flat=True)
        )
        rw_flags = [f for f in flags if f.flag_type == FlagType.REPEAT_WINNER]
        flagged_bidder_ids = {
            f.trigger_data.get("bidder_id") for f in rw_flags if f.trigger_data
        }
        overlap = focus_bidder_ids & flagged_bidder_ids
        assert not overlap, (
            f"Focus bidder (win_rate={wins}/{total}={wins/total:.3f}) "
            f"should not have REPEAT_WINNER flag, but was flagged: {overlap}"
        )


# ---------------------------------------------------------------------------
# Property 7d — SHORT_DEADLINE
# ---------------------------------------------------------------------------

class ShortDeadlinePBTTest(TestCase):
    """
    Property 7 (SHORT_DEADLINE): For any tender with deadline < 3 calendar
    days from publication, SHORT_DEADLINE (MEDIUM) is raised. For ≥3 days,
    it is not raised.
    Validates: Requirement 3.4
    """

    def setUp(self):
        _setup_rules()
        self.engine = FraudDetectionEngine()

    def _make_tender_with_delta(self, delta_seconds):
        global _tender_counter
        _tender_counter += 1
        pub = timezone.now() - timedelta(seconds=1)
        deadline = pub + timedelta(seconds=delta_seconds)
        return Tender.objects.create(
            tender_id=f"PBT-SD-{_tender_counter}",
            title="PBT Short Deadline",
            category="INFRA",
            estimated_value=Decimal("100000.00"),
            currency="INR",
            submission_deadline=deadline,
            buyer_id="PBT-SD-BUYER",
            buyer_name="PBT SD Buyer",
            publication_date=pub,
            created_at=pub,
        )

    @given(_st_short_delta)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_short_deadline_raises_flag(self, delta_seconds):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (SHORT_DEADLINE trigger)
        with patch("bids.tasks.compute_score_task.delay"):
            tender = self._make_tender_with_delta(delta_seconds)
            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.SHORT_DEADLINE in flag_types, (
            f"Expected SHORT_DEADLINE for delta={delta_seconds}s "
            f"({delta_seconds / 86400:.2f} days)"
        )
        sd_flags = [f for f in flags if f.flag_type == FlagType.SHORT_DEADLINE]
        assert sd_flags[0].severity == Severity.MEDIUM, (
            f"Expected MEDIUM severity, got {sd_flags[0].severity}"
        )

    @given(_st_long_delta)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_long_deadline_no_flag(self, delta_seconds):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (SHORT_DEADLINE no-trigger)
        with patch("bids.tasks.compute_score_task.delay"):
            tender = self._make_tender_with_delta(delta_seconds)
            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.SHORT_DEADLINE not in flag_types, (
            f"Expected no SHORT_DEADLINE for delta={delta_seconds}s "
            f"({delta_seconds / 86400:.2f} days)"
        )


# ---------------------------------------------------------------------------
# Property 7e — LINKED_ENTITIES
# ---------------------------------------------------------------------------

class LinkedEntitiesPBTTest(TestCase):
    """
    Property 7 (LINKED_ENTITIES): For any two bidders sharing an address or
    director, LINKED_ENTITIES (HIGH) is raised. For bidders with no shared
    attributes, it is not raised.
    Validates: Requirement 3.5
    """

    def setUp(self):
        _setup_rules()
        self.engine = FraudDetectionEngine()

    @given(_st_link_type)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_shared_attribute_raises_flag(self, link_type):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (LINKED_ENTITIES trigger)
        shared_value = f"Shared-{link_type}-PBT"

        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            if link_type == "address":
                b1 = _make_bidder(address=shared_value, directors="Dir LE-A")
                b2 = _make_bidder(address=shared_value, directors="Dir LE-B")
            else:
                b1 = _make_bidder(address="Addr LE-A", directors=shared_value)
                b2 = _make_bidder(address="Addr LE-B", directors=shared_value)

            _make_bid(tender, b1, "90000")
            _make_bid(tender, b2, "95000")

            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.LINKED_ENTITIES in flag_types, (
            f"Expected LINKED_ENTITIES for shared {link_type}"
        )
        le_flags = [f for f in flags if f.flag_type == FlagType.LINKED_ENTITIES]
        assert le_flags[0].severity == Severity.HIGH, (
            f"Expected HIGH severity, got {le_flags[0].severity}"
        )

    @given(st.integers(min_value=2, max_value=5))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_no_shared_attributes_no_flag(self, bidder_count):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (LINKED_ENTITIES no-trigger)
        with patch("bids.tasks.compute_score_task.delay"):
            tender = _make_tender()
            for i in range(bidder_count):
                bidder = _make_bidder(
                    address=f"Unique-LE-Addr-{tender.pk}-{i}",
                    directors=f"Unique-LE-Dir-{tender.pk}-{i}",
                )
                _make_bid(tender, bidder, str(90000 + i * 1000))

            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.LINKED_ENTITIES not in flag_types, (
            f"Expected no LINKED_ENTITIES for {bidder_count} bidders with distinct attributes"
        )


# ---------------------------------------------------------------------------
# Property 7f — COVER_BID_PATTERN
# ---------------------------------------------------------------------------

class CoverBidPatternPBTTest(TestCase):
    """
    Property 7 (COVER_BID_PATTERN): For any bidder submitting bids in ≥3
    tenders in the same category within 30 days with 0 wins,
    COVER_BID_PATTERN (HIGH) is raised. For <3 tenders or any wins,
    it is not raised.
    Validates: Requirement 3.6
    """

    def setUp(self):
        _setup_rules()
        self.engine = FraudDetectionEngine()

    def _build_cover_scenario(self, num_tenders, wins, category):
        cover = _make_bidder(
            address=f"Cover-Addr-{num_tenders}-{wins}",
            directors=f"Cover-Dir-{num_tenders}-{wins}",
        )
        winner = _make_bidder(
            address=f"Winner-Addr-{num_tenders}-{wins}",
            directors=f"Winner-Dir-{num_tenders}-{wins}",
        )
        now = timezone.now()
        tenders = []
        for i in range(num_tenders):
            t = _make_tender(category=category)
            tenders.append(t)
            ts = now - timedelta(days=i % 25)  # all within 30-day window
            if i < wins:
                _make_bid(t, cover, "80000", timestamp=ts)
                _make_bid(t, winner, "90000", timestamp=ts)
            else:
                _make_bid(t, winner, "80000", timestamp=ts)
                _make_bid(t, cover, "90000", timestamp=ts)
        return tenders[-1]

    @given(_st_triggering_cover_count)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_cover_bid_pattern_raises_flag(self, num_tenders):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (COVER_BID_PATTERN trigger)
        category = f"CAT-CB-{num_tenders}"

        with patch("bids.tasks.compute_score_task.delay"):
            tender = self._build_cover_scenario(num_tenders, wins=0, category=category)
            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.COVER_BID_PATTERN in flag_types, (
            f"Expected COVER_BID_PATTERN for {num_tenders} tenders with 0 wins"
        )
        cb_flags = [f for f in flags if f.flag_type == FlagType.COVER_BID_PATTERN]
        assert cb_flags[0].severity == Severity.HIGH, (
            f"Expected HIGH severity, got {cb_flags[0].severity}"
        )

    @given(_st_safe_cover_count)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_below_threshold_no_flag(self, num_tenders):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (COVER_BID_PATTERN no-trigger, count)
        category = f"CAT-CB-SAFE-{num_tenders}"

        with patch("bids.tasks.compute_score_task.delay"):
            tender = self._build_cover_scenario(num_tenders, wins=0, category=category)
            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.COVER_BID_PATTERN not in flag_types, (
            f"Expected no COVER_BID_PATTERN for only {num_tenders} tenders"
        )

    @given(_st_triggering_cover_count)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_with_wins_no_flag(self, num_tenders):
        # Feature: tender-shield, Property 7: Red Flag Rules Fire Correctly (COVER_BID_PATTERN no-trigger, wins)
        category = f"CAT-CB-WIN-{num_tenders}"

        with patch("bids.tasks.compute_score_task.delay"):
            # Give the cover bidder 1 win — should suppress the flag
            tender = self._build_cover_scenario(num_tenders, wins=1, category=category)
            flags = self.engine.evaluate_rules(tender.pk)

        flag_types = [f.flag_type for f in flags]
        assert FlagType.COVER_BID_PATTERN not in flag_types, (
            f"Expected no COVER_BID_PATTERN when cover bidder has ≥1 win "
            f"({num_tenders} tenders)"
        )
