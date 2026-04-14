"""
Unit tests for BehavioralTracker — metric computation, HIGH_RISK transitions,
no-delete policy, and API endpoints.

Covers:
- Property 13: Company Profile Metrics Correctness (Requirements 7.2)
- Property 14: HIGH_RISK Status Invariant (Requirements 7.3, 7.4)
- Requirement 7.6: 5-year retention (no hard-delete)
"""

import time
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from authentication.models import User, UserRole
from bids.models import Bid, Bidder
from companies.models import CompanyProfile, RiskStatus
from companies.tracker import BehavioralTracker
from detection.models import RedFlag, FlagType, Severity
from graph.models import CollusionRing
from scoring.models import FraudRiskScore
from tenders.models import Tender


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tender(tender_id="T001", category="IT", estimated_value=100_000):
    return Tender.objects.create(
        tender_id=tender_id,
        title=f"Tender {tender_id}",
        category=category,
        estimated_value=Decimal(str(estimated_value)),
        currency="INR",
        submission_deadline=timezone.now() + timedelta(days=30),
        buyer_id="B1",
        buyer_name="Buyer One",
    )


def make_bidder(bidder_id="BIDDER-1", name="Acme Corp"):
    return Bidder.objects.create(bidder_id=bidder_id, bidder_name=name)


def make_bid(bidder, tender, bid_amount, is_winner=False, days_ago=0):
    return Bid.objects.create(
        bid_id=f"BID-{bidder.bidder_id}-{tender.tender_id}-{days_ago}",
        tender=tender,
        bidder=bidder,
        bid_amount=Decimal(str(bid_amount)),
        submission_timestamp=timezone.now() - timedelta(days=days_ago),
        is_winner=is_winner,
    )


# ---------------------------------------------------------------------------
# Metric computation tests
# ---------------------------------------------------------------------------

class TestUpdateProfileMetrics(TestCase):
    def setUp(self):
        self.tracker = BehavioralTracker()
        self.bidder = make_bidder()

    def test_total_bids_and_wins(self):
        t1 = make_tender("T1")
        t2 = make_tender("T2")
        t3 = make_tender("T3")
        make_bid(self.bidder, t1, 90_000, is_winner=True)
        make_bid(self.bidder, t2, 95_000, is_winner=False)
        make_bid(self.bidder, t3, 80_000, is_winner=True)

        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertEqual(profile.total_bids, 3)
        self.assertEqual(profile.total_wins, 2)

    def test_win_rate_calculation(self):
        t1 = make_tender("T1")
        t2 = make_tender("T2")
        make_bid(self.bidder, t1, 100_000, is_winner=True)
        make_bid(self.bidder, t2, 100_000, is_winner=False)

        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertAlmostEqual(float(profile.win_rate), 0.5, places=4)

    def test_win_rate_zero_when_no_bids(self):
        profile = self.tracker.update_profile(self.bidder.pk)
        self.assertEqual(float(profile.win_rate), 0.0)

    def test_avg_bid_deviation(self):
        # estimated_value = 100_000; bid = 120_000 → deviation = 0.2
        t1 = make_tender("T1", estimated_value=100_000)
        make_bid(self.bidder, t1, 120_000)

        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertAlmostEqual(float(profile.avg_bid_deviation), 0.2, places=4)

    def test_avg_bid_deviation_multiple_bids(self):
        # bid1: |120k - 100k| / 100k = 0.2
        # bid2: |80k  - 100k| / 100k = 0.2
        # avg = 0.2
        t1 = make_tender("T1", estimated_value=100_000)
        t2 = make_tender("T2", estimated_value=100_000)
        make_bid(self.bidder, t1, 120_000)
        make_bid(self.bidder, t2, 80_000)

        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertAlmostEqual(float(profile.avg_bid_deviation), 0.2, places=4)

    def test_active_red_flag_count(self):
        t1 = make_tender("T1")
        make_bid(self.bidder, t1, 100_000)
        RedFlag.objects.create(
            tender=t1, bidder=self.bidder,
            flag_type=FlagType.SINGLE_BIDDER, severity=Severity.HIGH,
            is_active=True,
        )
        RedFlag.objects.create(
            tender=t1, bidder=self.bidder,
            flag_type=FlagType.PRICE_ANOMALY, severity=Severity.MEDIUM,
            is_active=False,  # cleared — should not count
        )

        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertEqual(profile.active_red_flag_count, 1)

    def test_highest_fraud_risk_score(self):
        t1 = make_tender("T1")
        t2 = make_tender("T2")
        make_bid(self.bidder, t1, 100_000)
        make_bid(self.bidder, t2, 100_000)
        FraudRiskScore.objects.create(tender=t1, score=45)
        FraudRiskScore.objects.create(tender=t2, score=82)

        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertEqual(profile.highest_fraud_risk_score, 82)

    def test_profile_created_if_not_exists(self):
        self.assertFalse(CompanyProfile.objects.filter(bidder=self.bidder).exists())
        self.tracker.update_profile(self.bidder.pk)
        self.assertTrue(CompanyProfile.objects.filter(bidder=self.bidder).exists())

    def test_profile_updated_on_second_call(self):
        t1 = make_tender("T1")
        make_bid(self.bidder, t1, 100_000, is_winner=True)
        self.tracker.update_profile(self.bidder.pk)

        t2 = make_tender("T2")
        make_bid(self.bidder, t2, 90_000, is_winner=False)
        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertEqual(profile.total_bids, 2)
        self.assertEqual(profile.total_wins, 1)


# ---------------------------------------------------------------------------
# HIGH_RISK status transition tests
# ---------------------------------------------------------------------------

class TestHighRiskTransitions(TestCase):
    def setUp(self):
        self.tracker = BehavioralTracker()
        self.bidder = make_bidder()

    def test_high_risk_when_category_win_rate_exceeds_60_percent(self):
        """Win rate > 60% in a single category within 12 months → HIGH_RISK."""
        category = "Construction"
        for i in range(7):
            t = make_tender(f"T{i}", category=category)
            make_bid(self.bidder, t, 100_000, is_winner=(i < 5))  # 5 wins out of 7

        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertEqual(profile.risk_status, RiskStatus.HIGH_RISK)

    def test_not_high_risk_when_category_win_rate_at_60_percent(self):
        """Win rate exactly 60% (not exceeding) should NOT trigger HIGH_RISK."""
        category = "IT"
        for i in range(5):
            t = make_tender(f"T{i}", category=category)
            make_bid(self.bidder, t, 100_000, is_winner=(i < 3))  # 3/5 = 60%

        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertNotEqual(profile.risk_status, RiskStatus.HIGH_RISK)

    def test_not_high_risk_when_wins_outside_rolling_window(self):
        """Wins older than 12 months should not count toward HIGH_RISK threshold."""
        category = "Roads"
        for i in range(5):
            # All bids placed 400 days ago — outside the 365-day window
            t = make_tender(f"T{i}", category=category)
            make_bid(self.bidder, t, 100_000, is_winner=True, days_ago=400)

        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertNotEqual(profile.risk_status, RiskStatus.HIGH_RISK)

    def test_flag_high_risk_sets_status(self):
        """flag_high_risk() must set risk_status = HIGH_RISK regardless of metrics."""
        self.tracker.update_profile(self.bidder.pk)  # creates profile with LOW status

        self.tracker.flag_high_risk(self.bidder.pk, reason="linked to collusion ring")

        profile = CompanyProfile.objects.get(bidder=self.bidder)
        self.assertEqual(profile.risk_status, RiskStatus.HIGH_RISK)

    def test_high_risk_preserved_after_update_profile(self):
        """Once HIGH_RISK is set, update_profile() must not downgrade it."""
        self.tracker.flag_high_risk(self.bidder.pk, reason="collusion ring")

        # Add a low-risk bid and recompute
        t = make_tender("T1")
        make_bid(self.bidder, t, 100_000, is_winner=False)
        profile = self.tracker.update_profile(self.bidder.pk)

        self.assertEqual(profile.risk_status, RiskStatus.HIGH_RISK)

    def test_high_risk_when_linked_to_collusion_ring(self):
        """Bidder linked to a CollusionRing → flag_high_risk() sets HIGH_RISK."""
        ring = CollusionRing.objects.create(
            ring_id="RING-001",
            member_bidder_ids=[self.bidder.pk],
            member_count=3,
        )
        profile, _ = CompanyProfile.objects.get_or_create(bidder=self.bidder)
        profile.collusion_ring = ring
        profile.save()

        self.tracker.flag_high_risk(self.bidder.pk, reason="CollusionRing RING-001")

        profile.refresh_from_db()
        self.assertEqual(profile.risk_status, RiskStatus.HIGH_RISK)


# ---------------------------------------------------------------------------
# No-delete retention policy tests
# ---------------------------------------------------------------------------

class TestRetentionPolicy(TestCase):
    def setUp(self):
        self.tracker = BehavioralTracker()
        self.bidder = make_bidder()

    def test_delete_raises_permission_denied(self):
        """CompanyProfile.delete() must raise PermissionDenied (Requirement 7.6)."""
        profile = self.tracker.update_profile(self.bidder.pk)

        with self.assertRaises(PermissionDenied):
            profile.delete()

    def test_profile_still_exists_after_failed_delete(self):
        profile = self.tracker.update_profile(self.bidder.pk)
        try:
            profile.delete()
        except PermissionDenied:
            pass

        self.assertTrue(CompanyProfile.objects.filter(pk=profile.pk).exists())


# ---------------------------------------------------------------------------
# Profile update timing test
# ---------------------------------------------------------------------------

class TestProfileUpdateTiming(TestCase):
    def test_update_profile_completes_within_10_seconds(self):
        """update_profile() must complete within 10 s (Requirement 7.1)."""
        bidder = make_bidder()
        # Create 50 bids across 50 tenders to simulate realistic load
        for i in range(50):
            t = make_tender(f"T{i}", category="IT")
            make_bid(bidder, t, 100_000 + i * 1000, is_winner=(i % 3 == 0))

        tracker = BehavioralTracker()
        start = time.monotonic()
        tracker.update_profile(bidder.pk)
        elapsed = time.monotonic() - start

        self.assertLess(elapsed, 10.0, f"update_profile took {elapsed:.2f}s — exceeds 10s limit")


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------

class TestCompanyAPIEndpoints(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.auditor = User.objects.create_user(
            username="auditor", email="a@test.com", password="pass", role=UserRole.AUDITOR
        )
        self.admin = User.objects.create_user(
            username="admin", email="b@test.com", password="pass", role=UserRole.ADMIN
        )
        self.bidder = make_bidder()
        self.tracker = BehavioralTracker()
        self.profile = self.tracker.update_profile(self.bidder.pk)

    def _auth(self, user):
        from rest_framework_simplejwt.tokens import AccessToken
        token = AccessToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def test_list_requires_auth(self):
        resp = self.client.get("/api/v1/companies/")
        self.assertEqual(resp.status_code, 401)

    def test_list_returns_profiles(self):
        self._auth(self.auditor)
        resp = self.client.get("/api/v1/companies/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("results", resp.data)
        self.assertEqual(resp.data["count"], 1)

    def test_detail_returns_profile(self):
        self._auth(self.auditor)
        resp = self.client.get(f"/api/v1/companies/{self.profile.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["bidder_id"], self.bidder.bidder_id)

    def test_detail_404_for_unknown(self):
        self._auth(self.auditor)
        resp = self.client.get("/api/v1/companies/99999/")
        self.assertEqual(resp.status_code, 404)

    def test_tenders_sub_resource(self):
        t = make_tender("T1")
        make_bid(self.bidder, t, 100_000)
        self._auth(self.auditor)
        resp = self.client.get(f"/api/v1/companies/{self.profile.pk}/tenders/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["tender_id"], "T1")

    def test_red_flags_sub_resource(self):
        t = make_tender("T1")
        make_bid(self.bidder, t, 100_000)
        RedFlag.objects.create(
            tender=t, bidder=self.bidder,
            flag_type=FlagType.SINGLE_BIDDER, severity=Severity.HIGH,
            is_active=True,
        )
        self._auth(self.auditor)
        resp = self.client.get(f"/api/v1/companies/{self.profile.pk}/red-flags/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["flag_type"], FlagType.SINGLE_BIDDER)

    def test_list_filter_by_risk_status(self):
        # Create a second bidder with HIGH_RISK
        b2 = make_bidder("BIDDER-2", "Beta Ltd")
        self.tracker.update_profile(b2.pk)
        self.tracker.flag_high_risk(b2.pk, "test")

        self._auth(self.auditor)
        resp = self.client.get("/api/v1/companies/?risk_status=HIGH_RISK")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["bidder_id"], "BIDDER-2")
