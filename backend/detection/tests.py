"""
Unit tests for FraudDetectionEngine — boundary-value tests for all 6 rules.

Each test creates the minimum DB fixtures needed, calls the engine directly,
and asserts on the returned RedFlag list.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from bids.models import Bid, Bidder
from detection.engine import FraudDetectionEngine
from detection.models import FlagType, RedFlag, RuleDefinition, Severity
from tenders.models import Tender


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tender(category="IT", estimated_value="100000.00", days_offset=10, **kwargs):
    """Create a Tender with sensible defaults."""
    now = timezone.now()
    return Tender.objects.create(
        tender_id=f"T-{Tender.objects.count() + 1}",
        title="Test Tender",
        category=category,
        estimated_value=Decimal(estimated_value),
        currency="INR",
        submission_deadline=now + timedelta(days=days_offset),
        buyer_id="BUYER-1",
        buyer_name="Test Buyer",
        created_at=now,
        **kwargs,
    )


def make_bidder(name="Bidder", address="123 Main St", directors="Alice"):
    """Create a Bidder."""
    count = Bidder.objects.count() + 1
    return Bidder.objects.create(
        bidder_id=f"B-{count}",
        bidder_name=f"{name} {count}",
        registered_address=address,
        director_names=directors,
    )


def make_bid(tender, bidder, amount="90000.00", timestamp=None):
    """Create a Bid."""
    count = Bid.objects.count() + 1
    return Bid.objects.create(
        bid_id=f"BID-{count}",
        tender=tender,
        bidder=bidder,
        bid_amount=Decimal(amount),
        submission_timestamp=timestamp or timezone.now(),
    )


def make_rule(rule_code, severity, parameters=None):
    """Create or get a RuleDefinition."""
    obj, _ = RuleDefinition.objects.get_or_create(
        rule_code=rule_code,
        defaults={
            "description": f"Auto-created rule for {rule_code}",
            "severity": severity,
            "is_active": True,
            "parameters": parameters or {},
        },
    )
    return obj


def setup_default_rules():
    """Ensure all 6 default rules exist in the DB."""
    make_rule(FlagType.SINGLE_BIDDER, Severity.HIGH, {})
    make_rule(FlagType.PRICE_ANOMALY, Severity.MEDIUM, {"threshold": "0.40"})
    make_rule(FlagType.REPEAT_WINNER, Severity.HIGH, {"threshold": 0.60})
    make_rule(FlagType.SHORT_DEADLINE, Severity.MEDIUM, {"min_days": 3})
    make_rule(FlagType.LINKED_ENTITIES, Severity.HIGH, {})
    make_rule(FlagType.COVER_BID_PATTERN, Severity.HIGH, {"window_days": 30, "min_bids": 3})


# ---------------------------------------------------------------------------
# SINGLE_BIDDER
# ---------------------------------------------------------------------------

class SingleBidderRuleTest(TestCase):
    def setUp(self):
        setup_default_rules()
        self.engine = FraudDetectionEngine()

    def test_exactly_one_bidder_fires(self):
        """Exactly 1 bidder → SINGLE_BIDDER flag raised."""
        tender = make_tender()
        bidder = make_bidder()
        make_bid(tender, bidder)

        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertIn(FlagType.SINGLE_BIDDER, flag_types)

    def test_two_bidders_does_not_fire(self):
        """2 bidders → SINGLE_BIDDER flag NOT raised."""
        tender = make_tender()
        b1 = make_bidder(address="Addr A")
        b2 = make_bidder(address="Addr B", directors="Bob")
        make_bid(tender, b1, "90000")
        make_bid(tender, b2, "95000")

        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.SINGLE_BIDDER, flag_types)

    def test_no_bids_does_not_fire(self):
        """0 bids → SINGLE_BIDDER flag NOT raised."""
        tender = make_tender()
        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.SINGLE_BIDDER, flag_types)


# ---------------------------------------------------------------------------
# PRICE_ANOMALY
# ---------------------------------------------------------------------------

class PriceAnomalyRuleTest(TestCase):
    def setUp(self):
        setup_default_rules()
        self.engine = FraudDetectionEngine()

    def _run(self, estimated, winning_bid):
        tender = make_tender(estimated_value=str(estimated))
        bidder = make_bidder()
        make_bid(tender, bidder, str(winning_bid))
        return self.engine.evaluate_rules(tender.pk)

    def test_exactly_40_percent_does_not_fire(self):
        """Exactly 40% deviation → does NOT fire (threshold is strictly >40%)."""
        # 100000 * 0.40 = 40000 deviation → winning bid = 60000
        flags = self._run(100000, 60000)
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.PRICE_ANOMALY, flag_types)

    def test_40_01_percent_fires(self):
        """40.01% deviation → fires."""
        # 100000 * 0.4001 = 40010 deviation → winning bid = 59990
        flags = self._run(100000, Decimal("59990.00"))
        flag_types = [f.flag_type for f in flags]
        self.assertIn(FlagType.PRICE_ANOMALY, flag_types)

    def test_negative_deviation_fires(self):
        """Winning bid above estimated by >40% → fires."""
        # 100000 * 1.41 = 141000 → deviation = 41%
        flags = self._run(100000, Decimal("141000.00"))
        flag_types = [f.flag_type for f in flags]
        self.assertIn(FlagType.PRICE_ANOMALY, flag_types)

    def test_negative_deviation_exactly_40_does_not_fire(self):
        """Winning bid above estimated by exactly 40% → does NOT fire."""
        flags = self._run(100000, Decimal("140000.00"))
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.PRICE_ANOMALY, flag_types)

    def test_severity_is_medium(self):
        """PRICE_ANOMALY severity must be MEDIUM."""
        flags = self._run(100000, Decimal("59990.00"))
        pa_flags = [f for f in flags if f.flag_type == FlagType.PRICE_ANOMALY]
        self.assertTrue(pa_flags)
        self.assertEqual(pa_flags[0].severity, Severity.MEDIUM)


# ---------------------------------------------------------------------------
# REPEAT_WINNER
# ---------------------------------------------------------------------------

class RepeatWinnerRuleTest(TestCase):
    def setUp(self):
        setup_default_rules()
        self.engine = FraudDetectionEngine()

    def _setup_wins(self, wins, total, category="IT"):
        """
        Create `total` tenders in `category`. The same bidder submits the
        lowest bid in `wins` of them. Returns (current_tender, bidder).
        """
        bidder = make_bidder(address="Unique Addr RW", directors="Director RW")
        other = make_bidder(address="Other Addr RW", directors="Other Dir RW")

        tenders = []
        for i in range(total):
            t = make_tender(category=category)
            tenders.append(t)
            if i < wins:
                # bidder wins (lowest bid)
                make_bid(t, bidder, "80000")
                make_bid(t, other, "90000")
            else:
                # other wins
                make_bid(t, other, "80000")
                make_bid(t, bidder, "90000")

        # The "current" tender is the last one
        return tenders[-1], bidder

    def test_exactly_60_percent_does_not_fire(self):
        """Exactly 60% win rate → does NOT fire (threshold is strictly >60%)."""
        # 3 wins out of 5 = 60%
        tender, _ = self._setup_wins(wins=3, total=5)
        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.REPEAT_WINNER, flag_types)

    def test_above_60_percent_fires(self):
        """4 wins out of 5 = 80% → fires."""
        tender, _ = self._setup_wins(wins=4, total=5)
        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertIn(FlagType.REPEAT_WINNER, flag_types)

    def test_severity_is_high(self):
        """REPEAT_WINNER severity must be HIGH."""
        tender, _ = self._setup_wins(wins=4, total=5)
        flags = self.engine.evaluate_rules(tender.pk)
        rw_flags = [f for f in flags if f.flag_type == FlagType.REPEAT_WINNER]
        self.assertTrue(rw_flags)
        self.assertEqual(rw_flags[0].severity, Severity.HIGH)


# ---------------------------------------------------------------------------
# SHORT_DEADLINE
# ---------------------------------------------------------------------------

class ShortDeadlineRuleTest(TestCase):
    def setUp(self):
        setup_default_rules()
        self.engine = FraudDetectionEngine()

    def _make_tender_with_deadline(self, delta_seconds):
        now = timezone.now()
        pub = now - timedelta(seconds=1)  # published just now
        deadline = pub + timedelta(seconds=delta_seconds)
        return Tender.objects.create(
            tender_id=f"T-SD-{Tender.objects.count() + 1}",
            title="Short Deadline Tender",
            category="INFRA",
            estimated_value=Decimal("100000.00"),
            currency="INR",
            submission_deadline=deadline,
            buyer_id="BUYER-SD",
            buyer_name="SD Buyer",
            publication_date=pub,
            created_at=pub,
        )

    def test_exactly_3_days_does_not_fire(self):
        """Exactly 3 calendar days (3 * 86400 s) → does NOT fire."""
        tender = self._make_tender_with_deadline(3 * 86400)
        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.SHORT_DEADLINE, flag_types)

    def test_2_days_23_hours_fires(self):
        """2 days 23 hours = 2*86400 + 23*3600 = 255600 s < 3 days → fires."""
        delta = 2 * 86400 + 23 * 3600
        tender = self._make_tender_with_deadline(delta)
        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertIn(FlagType.SHORT_DEADLINE, flag_types)

    def test_1_day_fires(self):
        """1 day → fires."""
        tender = self._make_tender_with_deadline(86400)
        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertIn(FlagType.SHORT_DEADLINE, flag_types)

    def test_severity_is_medium(self):
        """SHORT_DEADLINE severity must be MEDIUM."""
        tender = self._make_tender_with_deadline(86400)
        flags = self.engine.evaluate_rules(tender.pk)
        sd_flags = [f for f in flags if f.flag_type == FlagType.SHORT_DEADLINE]
        self.assertTrue(sd_flags)
        self.assertEqual(sd_flags[0].severity, Severity.MEDIUM)


# ---------------------------------------------------------------------------
# LINKED_ENTITIES
# ---------------------------------------------------------------------------

class LinkedEntitiesRuleTest(TestCase):
    def setUp(self):
        setup_default_rules()
        self.engine = FraudDetectionEngine()

    def test_shared_address_fires(self):
        """Two bidders with same registered_address → LINKED_ENTITIES fires."""
        tender = make_tender()
        b1 = make_bidder(address="Shared Address 1", directors="Dir A")
        b2 = make_bidder(address="Shared Address 1", directors="Dir B")
        make_bid(tender, b1, "90000")
        make_bid(tender, b2, "95000")

        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertIn(FlagType.LINKED_ENTITIES, flag_types)

    def test_shared_director_fires(self):
        """Two bidders sharing a director name → LINKED_ENTITIES fires."""
        tender = make_tender()
        b1 = make_bidder(address="Addr X1", directors="Shared Director")
        b2 = make_bidder(address="Addr X2", directors="Shared Director")
        make_bid(tender, b1, "90000")
        make_bid(tender, b2, "95000")

        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertIn(FlagType.LINKED_ENTITIES, flag_types)

    def test_no_sharing_does_not_fire(self):
        """Two bidders with different address and directors → does NOT fire."""
        tender = make_tender()
        b1 = make_bidder(address="Unique Addr 1", directors="Director One")
        b2 = make_bidder(address="Unique Addr 2", directors="Director Two")
        make_bid(tender, b1, "90000")
        make_bid(tender, b2, "95000")

        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.LINKED_ENTITIES, flag_types)

    def test_single_bidder_does_not_fire(self):
        """Only 1 bidder → LINKED_ENTITIES does NOT fire (need ≥2)."""
        tender = make_tender()
        b1 = make_bidder(address="Solo Addr", directors="Solo Dir")
        make_bid(tender, b1, "90000")

        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.LINKED_ENTITIES, flag_types)

    def test_severity_is_high(self):
        """LINKED_ENTITIES severity must be HIGH."""
        tender = make_tender()
        b1 = make_bidder(address="Shared Addr LE", directors="Dir LE A")
        b2 = make_bidder(address="Shared Addr LE", directors="Dir LE B")
        make_bid(tender, b1, "90000")
        make_bid(tender, b2, "95000")

        flags = self.engine.evaluate_rules(tender.pk)
        le_flags = [f for f in flags if f.flag_type == FlagType.LINKED_ENTITIES]
        self.assertTrue(le_flags)
        self.assertEqual(le_flags[0].severity, Severity.HIGH)


# ---------------------------------------------------------------------------
# COVER_BID_PATTERN
# ---------------------------------------------------------------------------

class CoverBidPatternRuleTest(TestCase):
    def setUp(self):
        setup_default_rules()
        self.engine = FraudDetectionEngine()

    def _setup_cover_bids(self, num_tenders, wins=0, category="ROADS"):
        """
        Create `num_tenders` tenders in `category` within the last 30 days.
        The cover bidder bids on all of them and wins `wins` of them.
        Returns the last tender (the one we evaluate).
        """
        cover_bidder = make_bidder(address="Cover Addr", directors="Cover Dir")
        winner_bidder = make_bidder(address="Winner Addr", directors="Winner Dir")

        now = timezone.now()
        tenders = []
        for i in range(num_tenders):
            t = make_tender(category=category)
            tenders.append(t)
            ts = now - timedelta(days=i)  # within 30-day window
            if i < wins:
                # cover bidder wins
                make_bid(t, cover_bidder, "80000", timestamp=ts)
                make_bid(t, winner_bidder, "90000", timestamp=ts)
            else:
                # cover bidder loses
                make_bid(t, winner_bidder, "80000", timestamp=ts)
                make_bid(t, cover_bidder, "90000", timestamp=ts)

        return tenders[-1], cover_bidder

    def test_exactly_3_tenders_0_wins_fires(self):
        """3 tenders, 0 wins in 30 days → COVER_BID_PATTERN fires."""
        tender, _ = self._setup_cover_bids(num_tenders=3, wins=0)
        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertIn(FlagType.COVER_BID_PATTERN, flag_types)

    def test_2_tenders_does_not_fire(self):
        """2 tenders, 0 wins → does NOT fire (need ≥3)."""
        tender, _ = self._setup_cover_bids(num_tenders=2, wins=0)
        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.COVER_BID_PATTERN, flag_types)

    def test_3_tenders_1_win_does_not_fire(self):
        """3 tenders but 1 win → does NOT fire (wins > 0)."""
        tender, _ = self._setup_cover_bids(num_tenders=3, wins=1)
        flags = self.engine.evaluate_rules(tender.pk)
        flag_types = [f.flag_type for f in flags]
        self.assertNotIn(FlagType.COVER_BID_PATTERN, flag_types)

    def test_severity_is_high(self):
        """COVER_BID_PATTERN severity must be HIGH."""
        tender, _ = self._setup_cover_bids(num_tenders=3, wins=0)
        flags = self.engine.evaluate_rules(tender.pk)
        cb_flags = [f for f in flags if f.flag_type == FlagType.COVER_BID_PATTERN]
        self.assertTrue(cb_flags)
        self.assertEqual(cb_flags[0].severity, Severity.HIGH)


# ---------------------------------------------------------------------------
# Flag clearing (hot-reload / sync)
# ---------------------------------------------------------------------------

class FlagClearingTest(TestCase):
    def setUp(self):
        setup_default_rules()
        self.engine = FraudDetectionEngine()

    def test_flag_cleared_when_condition_no_longer_holds(self):
        """
        A SINGLE_BIDDER flag raised on first evaluation should be cleared
        when a second bidder is added and the engine re-evaluates.
        """
        tender = make_tender()
        b1 = make_bidder(address="Addr Clear 1", directors="Dir Clear 1")
        make_bid(tender, b1, "90000")

        # First evaluation — flag should be raised
        flags = self.engine.evaluate_rules(tender.pk)
        self.assertTrue(any(f.flag_type == FlagType.SINGLE_BIDDER for f in flags))

        # Add a second bidder
        b2 = make_bidder(address="Addr Clear 2", directors="Dir Clear 2")
        make_bid(tender, b2, "95000")

        # Second evaluation — SINGLE_BIDDER should be cleared
        flags2 = self.engine.evaluate_rules(tender.pk)
        self.assertFalse(any(f.flag_type == FlagType.SINGLE_BIDDER for f in flags2))

        # Verify the DB record is cleared
        cleared = RedFlag.objects.filter(
            tender=tender, flag_type=FlagType.SINGLE_BIDDER, is_active=False
        )
        self.assertTrue(cleared.exists())
