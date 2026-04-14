"""
Unit tests for CollusionGraph — edge creation, ring detection, and alert triggering.

Covers:
  - CO_BID edge created for every bidder pair on the same tender
  - SHARED_DIRECTOR edge created when bidders share a director name
  - SHARED_ADDRESS edge created when bidders share a registered address
  - Collusion ring NOT created for exactly 2 nodes (below threshold)
  - Collusion ring IS created for exactly 3 nodes (at threshold)
  - Collusion ring IS created for > 3 nodes
  - Alert records created for all AUDITOR/ADMIN users when a ring is detected
  - Company profiles flagged HIGH_RISK for ring members
  - Idempotency: re-running update_graph does not duplicate edges
"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from authentication.models import User, UserRole
from bids.models import Bid, Bidder
from detection.models import RedFlag, FlagType, Severity
from graph.collusion_graph import CollusionGraph
from graph.models import CollusionRing, EdgeType, GraphEdge, GraphNode
from scoring.models import FraudRiskScore
from tenders.models import Tender


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_tender_counter = 0
_bidder_counter = 0
_bid_counter = 0


def make_tender(category="IT", estimated_value="100000.00"):
    global _tender_counter
    _tender_counter += 1
    return Tender.objects.create(
        tender_id=f"T-{_tender_counter}",
        title=f"Tender {_tender_counter}",
        category=category,
        estimated_value=Decimal(estimated_value),
        currency="INR",
        submission_deadline=timezone.now() + timezone.timedelta(days=10),
        buyer_id="BUYER-1",
        buyer_name="Test Buyer",
    )


def make_bidder(name="Bidder", address="123 Main St", directors="Alice"):
    global _bidder_counter
    _bidder_counter += 1
    return Bidder.objects.create(
        bidder_id=f"B-{_bidder_counter}",
        bidder_name=f"{name} {_bidder_counter}",
        registered_address=address,
        director_names=directors,
    )


def make_bid(tender, bidder, amount="90000.00"):
    global _bid_counter
    _bid_counter += 1
    return Bid.objects.create(
        bid_id=f"BID-{_bid_counter}",
        tender=tender,
        bidder=bidder,
        bid_amount=Decimal(amount),
        submission_timestamp=timezone.now(),
    )


def make_high_red_flag(tender, bidder=None):
    return RedFlag.objects.create(
        tender=tender,
        bidder=bidder,
        flag_type=FlagType.SINGLE_BIDDER,
        severity=Severity.HIGH,
        is_active=True,
    )


def make_fraud_score(tender, score=80):
    return FraudRiskScore.objects.create(
        tender=tender,
        score=score,
        ml_anomaly_score=None,
        ml_collusion_score=None,
        red_flag_contribution=score,
        model_version="test",
        weight_config={},
    )


# ---------------------------------------------------------------------------
# CO_BID edge tests
# ---------------------------------------------------------------------------

class CoBidEdgeTests(TestCase):
    def setUp(self):
        self.graph = CollusionGraph()

    def test_co_bid_edge_created_for_two_bidders(self):
        """Two bidders on the same tender → one CO_BID edge."""
        tender = make_tender()
        b1 = make_bidder("Alpha")
        b2 = make_bidder("Beta")
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)

        edges = GraphEdge.objects.filter(edge_type=EdgeType.CO_BID)
        self.assertEqual(edges.count(), 1)

    def test_co_bid_edge_created_for_three_bidders(self):
        """Three bidders on the same tender → three CO_BID edges (C(3,2)=3)."""
        tender = make_tender()
        bidders = [make_bidder(f"Bidder{i}") for i in range(3)]
        for b in bidders:
            make_bid(tender, b)

        self.graph.update_graph(tender.pk)

        edges = GraphEdge.objects.filter(edge_type=EdgeType.CO_BID)
        self.assertEqual(edges.count(), 3)

    def test_no_co_bid_edge_for_single_bidder(self):
        """Single bidder on a tender → no CO_BID edges."""
        tender = make_tender()
        b = make_bidder()
        make_bid(tender, b)

        self.graph.update_graph(tender.pk)

        self.assertEqual(GraphEdge.objects.filter(edge_type=EdgeType.CO_BID).count(), 0)

    def test_co_bid_idempotent(self):
        """Running update_graph twice does not duplicate CO_BID edges."""
        tender = make_tender()
        b1 = make_bidder("X")
        b2 = make_bidder("Y")
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)
        self.graph.update_graph(tender.pk)

        self.assertEqual(GraphEdge.objects.filter(edge_type=EdgeType.CO_BID).count(), 1)

    def test_graph_nodes_upserted(self):
        """GraphNode is created for each bidder."""
        tender = make_tender()
        b1 = make_bidder("NodeA")
        b2 = make_bidder("NodeB")
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)

        self.assertEqual(GraphNode.objects.count(), 2)


# ---------------------------------------------------------------------------
# SHARED_DIRECTOR edge tests
# ---------------------------------------------------------------------------

class SharedDirectorEdgeTests(TestCase):
    def setUp(self):
        self.graph = CollusionGraph()

    def test_shared_director_edge_created(self):
        """Two bidders sharing a director name → SHARED_DIRECTOR edge."""
        tender = make_tender()
        b1 = make_bidder("Corp A", directors="John Smith,Jane Doe")
        b2 = make_bidder("Corp B", directors="John Smith,Bob Jones")
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)

        edges = GraphEdge.objects.filter(edge_type=EdgeType.SHARED_DIRECTOR)
        self.assertEqual(edges.count(), 1)

    def test_no_shared_director_edge_when_different_directors(self):
        """Two bidders with no common directors → no SHARED_DIRECTOR edge."""
        tender = make_tender()
        b1 = make_bidder("Corp A", directors="Alice")
        b2 = make_bidder("Corp B", directors="Bob")
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)

        self.assertEqual(GraphEdge.objects.filter(edge_type=EdgeType.SHARED_DIRECTOR).count(), 0)

    def test_shared_director_edge_idempotent(self):
        """Running update_graph twice does not duplicate SHARED_DIRECTOR edges."""
        tender = make_tender()
        b1 = make_bidder("Corp A", directors="Shared Director")
        b2 = make_bidder("Corp B", directors="Shared Director")
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)
        self.graph.update_graph(tender.pk)

        self.assertEqual(GraphEdge.objects.filter(edge_type=EdgeType.SHARED_DIRECTOR).count(), 1)


# ---------------------------------------------------------------------------
# SHARED_ADDRESS edge tests
# ---------------------------------------------------------------------------

class SharedAddressEdgeTests(TestCase):
    def setUp(self):
        self.graph = CollusionGraph()

    def test_shared_address_edge_created(self):
        """Two bidders sharing a registered address → SHARED_ADDRESS edge."""
        shared_addr = "42 Fraud Lane, Mumbai"
        tender = make_tender()
        b1 = make_bidder("Corp A", address=shared_addr)
        b2 = make_bidder("Corp B", address=shared_addr)
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)

        edges = GraphEdge.objects.filter(edge_type=EdgeType.SHARED_ADDRESS)
        self.assertEqual(edges.count(), 1)

    def test_no_shared_address_edge_when_different_addresses(self):
        """Two bidders with different addresses → no SHARED_ADDRESS edge."""
        tender = make_tender()
        b1 = make_bidder("Corp A", address="1 Alpha St")
        b2 = make_bidder("Corp B", address="2 Beta Ave")
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)

        self.assertEqual(GraphEdge.objects.filter(edge_type=EdgeType.SHARED_ADDRESS).count(), 0)

    def test_shared_address_case_insensitive(self):
        """Address comparison is case-insensitive."""
        tender = make_tender()
        b1 = make_bidder("Corp A", address="42 Fraud Lane")
        b2 = make_bidder("Corp B", address="42 fraud lane")
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)

        self.assertEqual(GraphEdge.objects.filter(edge_type=EdgeType.SHARED_ADDRESS).count(), 1)

    def test_shared_address_edge_idempotent(self):
        """Running update_graph twice does not duplicate SHARED_ADDRESS edges."""
        addr = "99 Collusion Road"
        tender = make_tender()
        b1 = make_bidder("Corp A", address=addr)
        b2 = make_bidder("Corp B", address=addr)
        make_bid(tender, b1)
        make_bid(tender, b2)

        self.graph.update_graph(tender.pk)
        self.graph.update_graph(tender.pk)

        self.assertEqual(GraphEdge.objects.filter(edge_type=EdgeType.SHARED_ADDRESS).count(), 1)


# ---------------------------------------------------------------------------
# Collusion ring detection threshold tests
# ---------------------------------------------------------------------------

class CollusionRingDetectionTests(TestCase):
    def setUp(self):
        self.graph = CollusionGraph()

    def _setup_bidders_on_tender(self, n: int):
        """Create n bidders all bidding on the same tender with a HIGH red flag."""
        tender = make_tender()
        bidders = [make_bidder(f"RingBidder{i}") for i in range(n)]
        for b in bidders:
            make_bid(tender, b)
        make_high_red_flag(tender)
        make_fraud_score(tender)
        self.graph.update_graph(tender.pk)
        return tender, bidders

    def test_no_ring_for_two_nodes(self):
        """Exactly 2 nodes → below threshold → no CollusionRing created."""
        self._setup_bidders_on_tender(2)
        rings = self.graph.detect_collusion_rings()
        self.assertEqual(len(rings), 0)
        self.assertEqual(CollusionRing.objects.count(), 0)

    def test_ring_created_for_exactly_three_nodes(self):
        """Exactly 3 nodes connected by HIGH-severity red flag edges → ring created."""
        self._setup_bidders_on_tender(3)
        rings = self.graph.detect_collusion_rings()
        self.assertEqual(len(rings), 1)
        self.assertEqual(CollusionRing.objects.count(), 1)
        ring = CollusionRing.objects.first()
        self.assertEqual(ring.member_count, 3)

    def test_ring_created_for_more_than_three_nodes(self):
        """5 nodes connected by HIGH-severity red flag edges → ring created."""
        self._setup_bidders_on_tender(5)
        rings = self.graph.detect_collusion_rings()
        self.assertEqual(len(rings), 1)
        ring = CollusionRing.objects.first()
        self.assertEqual(ring.member_count, 5)

    def test_ring_has_unique_identifier(self):
        """Each CollusionRing gets a unique UUID ring_id."""
        self._setup_bidders_on_tender(3)
        self.graph.detect_collusion_rings()
        ring = CollusionRing.objects.first()
        self.assertIsNotNone(ring.ring_id)
        self.assertTrue(len(ring.ring_id) > 0)

    def test_ring_detection_idempotent(self):
        """Running detect_collusion_rings twice does not create duplicate rings."""
        self._setup_bidders_on_tender(3)
        self.graph.detect_collusion_rings()
        self.graph.detect_collusion_rings()
        self.assertEqual(CollusionRing.objects.count(), 1)

    def test_no_ring_without_high_severity_flags(self):
        """3 nodes but no HIGH-severity red flags → no ring created."""
        tender = make_tender()
        bidders = [make_bidder(f"NoBidder{i}") for i in range(3)]
        for b in bidders:
            make_bid(tender, b)
        # Only MEDIUM flag — should not trigger ring detection
        RedFlag.objects.create(
            tender=tender,
            flag_type=FlagType.PRICE_ANOMALY,
            severity=Severity.MEDIUM,
            is_active=True,
        )
        self.graph.update_graph(tender.pk)
        rings = self.graph.detect_collusion_rings()
        self.assertEqual(len(rings), 0)


# ---------------------------------------------------------------------------
# Alert triggering tests
# ---------------------------------------------------------------------------

class CollusionRingAlertTests(TestCase):
    def setUp(self):
        self.graph = CollusionGraph()
        # Create users to receive alerts
        self.auditor = User.objects.create_user(
            username="auditor1", email="auditor@test.com", password="pass", role=UserRole.AUDITOR
        )
        self.admin = User.objects.create_user(
            username="admin1", email="admin@test.com", password="pass", role=UserRole.ADMIN
        )

    def _setup_ring(self, n=3):
        tender = make_tender()
        bidders = [make_bidder(f"AlertBidder{i}") for i in range(n)]
        for b in bidders:
            make_bid(tender, b)
        make_high_red_flag(tender)
        make_fraud_score(tender, score=85)
        self.graph.update_graph(tender.pk)
        return tender, bidders

    def test_alerts_created_for_all_users_on_ring_detection(self):
        """Alert records are created for all AUDITOR and ADMIN users when a ring is detected."""
        from alerts.models import Alert
        self._setup_ring(3)
        self.graph.detect_collusion_rings()

        alerts = Alert.objects.all()
        # One alert per user (auditor + admin = 2)
        self.assertEqual(alerts.count(), 2)
        user_ids = set(alerts.values_list("user_id", flat=True))
        self.assertIn(self.auditor.pk, user_ids)
        self.assertIn(self.admin.pk, user_ids)

    def test_alert_type_is_collusion_ring(self):
        """Alerts triggered by ring detection have alert_type=COLLUSION_RING."""
        from alerts.models import Alert, AlertType
        self._setup_ring(3)
        self.graph.detect_collusion_rings()

        for alert in Alert.objects.all():
            self.assertEqual(alert.alert_type, AlertType.COLLUSION_RING)

    def test_alert_contains_fraud_score(self):
        """Alert records include the fraud_risk_score."""
        from alerts.models import Alert
        self._setup_ring(3)
        self.graph.detect_collusion_rings()

        for alert in Alert.objects.all():
            self.assertGreater(alert.fraud_risk_score, 0)

    def test_ring_members_flagged_high_risk(self):
        """All bidders in a detected ring have their company profile set to HIGH_RISK."""
        from companies.models import CompanyProfile, RiskStatus
        tender, bidders = self._setup_ring(3)
        self.graph.detect_collusion_rings()

        for bidder in bidders:
            profile = CompanyProfile.objects.get(bidder=bidder)
            self.assertEqual(profile.risk_status, RiskStatus.HIGH_RISK)

    def test_no_alerts_when_no_ring(self):
        """No alerts created when ring detection finds no rings (only 2 nodes)."""
        from alerts.models import Alert
        tender = make_tender()
        b1 = make_bidder("Solo1")
        b2 = make_bidder("Solo2")
        make_bid(tender, b1)
        make_bid(tender, b2)
        make_high_red_flag(tender)
        make_fraud_score(tender)
        self.graph.update_graph(tender.pk)
        self.graph.detect_collusion_rings()

        self.assertEqual(Alert.objects.count(), 0)


# ---------------------------------------------------------------------------
# Graph data API tests
# ---------------------------------------------------------------------------

class GraphDataTests(TestCase):
    def setUp(self):
        self.graph = CollusionGraph()

    def test_get_graph_data_returns_nodes_and_edges(self):
        """get_graph_data returns dict with 'nodes' and 'edges' keys."""
        tender = make_tender()
        b1 = make_bidder("DataA")
        b2 = make_bidder("DataB")
        make_bid(tender, b1)
        make_bid(tender, b2)
        self.graph.update_graph(tender.pk)

        data = self.graph.get_graph_data()
        self.assertIn("nodes", data)
        self.assertIn("edges", data)
        self.assertEqual(len(data["nodes"]), 2)
        self.assertGreaterEqual(len(data["edges"]), 1)

    def test_get_graph_data_edge_type_filter(self):
        """get_graph_data with edge_type filter returns only matching edges."""
        tender = make_tender()
        b1 = make_bidder("FilterA", directors="Shared")
        b2 = make_bidder("FilterB", directors="Shared")
        make_bid(tender, b1)
        make_bid(tender, b2)
        self.graph.update_graph(tender.pk)

        co_bid_data = self.graph.get_graph_data(edge_type=EdgeType.CO_BID)
        for edge in co_bid_data["edges"]:
            self.assertEqual(edge["type"], EdgeType.CO_BID)

        director_data = self.graph.get_graph_data(edge_type=EdgeType.SHARED_DIRECTOR)
        for edge in director_data["edges"]:
            self.assertEqual(edge["type"], EdgeType.SHARED_DIRECTOR)
