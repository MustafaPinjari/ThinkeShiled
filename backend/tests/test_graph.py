# Feature: tender-shield, Property 15: Collusion Graph Edge Invariants
# Feature: tender-shield, Property 16: Collusion Ring Detection
#
# Property 15: For any two bidders co-bidding on the same tender, a CO_BID
# edge must exist between their graph nodes. For any two bidders sharing a
# director name, a SHARED_DIRECTOR edge must exist. For any two bidders
# sharing a registered address, a SHARED_ADDRESS edge must exist.
# Validates: Requirements 8.1, 8.2, 8.3
#
# Property 16: For any connected component in the collusion graph containing
# 3 or more bidder nodes connected by HIGH-severity RedFlag edges, a
# CollusionRing must be created with a unique identifier, and an Alert with
# severity HIGH must be triggered.
# Validates: Requirements 8.4, 8.7

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from itertools import combinations
from typing import List

from django.utils import timezone
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

from alerts.models import Alert, AlertType
from authentication.models import User, UserRole
from bids.models import Bid, Bidder
from detection.models import FlagType, RedFlag, RuleDefinition, Severity
from graph.collusion_graph import CollusionGraph
from graph.models import CollusionRing, EdgeType, GraphEdge, GraphNode
from tenders.models import Tender

# ---------------------------------------------------------------------------
# Dataclasses used as strategy targets
# ---------------------------------------------------------------------------


@dataclass
class BidderSpec:
    """Compact description of a bidder for graph PBT strategies."""
    registered_address: str
    director_names: str  # comma-separated


# ---------------------------------------------------------------------------
# Counters for unique IDs
# ---------------------------------------------------------------------------

_counter = 0


def _uid(prefix: str) -> str:
    global _counter
    _counter += 1
    return f"{prefix}-GRAPH-PBT-{_counter}"


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _make_tender(category: str = "IT") -> Tender:
    return Tender.objects.create(
        tender_id=_uid("T"),
        title="Graph PBT Tender",
        category=category,
        estimated_value=Decimal("100000.00"),
        currency="INR",
        submission_deadline=timezone.now() + timedelta(days=30),
        buyer_id="PBT-BUYER",
        buyer_name="PBT Buyer",
    )


def _make_bidder(address: str = "", directors: str = "") -> Bidder:
    return Bidder.objects.create(
        bidder_id=_uid("BIDDER"),
        bidder_name="Graph PBT Corp",
        registered_address=address,
        director_names=directors,
    )


def _make_bid(tender: Tender, bidder: Bidder) -> Bid:
    return Bid.objects.create(
        bid_id=_uid("BID"),
        tender=tender,
        bidder=bidder,
        bid_amount=Decimal("90000.00"),
        submission_timestamp=timezone.now(),
    )


def _make_high_red_flag(tender: Tender, bidder: Bidder) -> RedFlag:
    """Create an active HIGH-severity RedFlag for a tender/bidder pair."""
    return RedFlag.objects.create(
        tender=tender,
        bidder=bidder,
        flag_type=FlagType.SINGLE_BIDDER,
        severity=Severity.HIGH,
        rule_version="1.0",
        trigger_data={"bid_count": 1},
        is_active=True,
    )


def _make_user(role: str = UserRole.AUDITOR) -> User:
    return User.objects.create_user(
        username=_uid("user"),
        email=f"{_uid('user')}@test.com",
        password="testpass123",
        role=role,
    )


def _edge_exists(
    node_a: GraphNode,
    node_b: GraphNode,
    edge_type: str,
    tender_id: int = None,
) -> bool:
    """
    Check whether an edge of *edge_type* exists between node_a and node_b
    in either direction (edges are stored with normalised direction).
    """
    qs = GraphEdge.objects.filter(edge_type=edge_type)
    if tender_id is not None:
        qs = qs.filter(tender_id=tender_id)
    return qs.filter(
        source_node__in=[node_a, node_b],
        target_node__in=[node_a, node_b],
    ).exists()


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_address_st = st.sampled_from([
    "123 Main St",
    "456 Oak Ave",
    "789 Pine Rd",
    "321 Elm Blvd",
    "654 Maple Dr",
])

_director_st = st.sampled_from([
    "Alice Smith",
    "Bob Jones",
    "Carol White",
    "David Brown",
    "Eve Davis",
])

_bidder_spec_st = st.builds(
    BidderSpec,
    registered_address=_address_st,
    director_names=_director_st,
)

# List of 2–6 bidder specs for a single tender
_bidder_list_st = st.lists(_bidder_spec_st, min_size=2, max_size=6)


# ===========================================================================
# Property 15 — Collusion Graph Edge Invariants
# ===========================================================================


class CollusionGraphEdgeInvariantsPropertyTest(TestCase):
    """
    Property 15: For any two bidders co-bidding on the same tender, a CO_BID
    edge must exist between their graph nodes. For any two bidders sharing a
    director name, a SHARED_DIRECTOR edge must exist. For any two bidders
    sharing a registered address, a SHARED_ADDRESS edge must exist.
    Validates: Requirements 8.1, 8.2, 8.3
    """

    # ------------------------------------------------------------------ #
    # 15a — CO_BID edges                                                  #
    # ------------------------------------------------------------------ #

    @given(_bidder_list_st)
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_co_bid_edge_exists_for_every_bidder_pair(self, specs: List[BidderSpec]):
        # Feature: tender-shield, Property 15: Collusion Graph Edge Invariants (CO_BID)
        #
        # For any two bidders who both submit bids on the same tender,
        # a CO_BID edge must exist between their graph nodes.
        tender = _make_tender()
        bidders = [_make_bidder(s.registered_address, s.director_names) for s in specs]
        for bidder in bidders:
            _make_bid(tender, bidder)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)

        # Every pair must have a CO_BID edge
        for b1, b2 in combinations(bidders, 2):
            node1 = GraphNode.objects.get(bidder=b1)
            node2 = GraphNode.objects.get(bidder=b2)
            assert _edge_exists(node1, node2, EdgeType.CO_BID, tender_id=tender.pk), (
                f"Expected CO_BID edge between bidder {b1.bidder_id} and "
                f"{b2.bidder_id} on tender {tender.pk}"
            )

    @given(st.integers(min_value=2, max_value=6))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_co_bid_edge_count_equals_n_choose_2(self, n: int):
        # Feature: tender-shield, Property 15: Collusion Graph Edge Invariants (CO_BID count)
        #
        # For n bidders on a single tender, exactly C(n,2) CO_BID edges must
        # be created (one per unique pair).
        tender = _make_tender()
        bidders = [
            _make_bidder(f"Addr-{_uid('A')}", f"Dir-{_uid('D')}")
            for _ in range(n)
        ]
        for bidder in bidders:
            _make_bid(tender, bidder)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)

        expected_count = n * (n - 1) // 2
        actual_count = GraphEdge.objects.filter(
            edge_type=EdgeType.CO_BID,
            tender_id=tender.pk,
        ).count()
        assert actual_count == expected_count, (
            f"Expected {expected_count} CO_BID edges for {n} bidders, "
            f"got {actual_count}"
        )

    @given(st.integers(min_value=2, max_value=4))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_co_bid_edges_are_idempotent(self, n: int):
        # Feature: tender-shield, Property 15: Collusion Graph Edge Invariants (CO_BID idempotent)
        #
        # Calling update_graph() twice must not create duplicate CO_BID edges.
        tender = _make_tender()
        bidders = [
            _make_bidder(f"Addr-{_uid('A')}", f"Dir-{_uid('D')}")
            for _ in range(n)
        ]
        for bidder in bidders:
            _make_bid(tender, bidder)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        graph.update_graph(tender.pk)  # second call — must be idempotent

        expected_count = n * (n - 1) // 2
        actual_count = GraphEdge.objects.filter(
            edge_type=EdgeType.CO_BID,
            tender_id=tender.pk,
        ).count()
        assert actual_count == expected_count, (
            f"Duplicate CO_BID edges after second update_graph() call: "
            f"expected {expected_count}, got {actual_count}"
        )

    # ------------------------------------------------------------------ #
    # 15b — SHARED_DIRECTOR edges                                         #
    # ------------------------------------------------------------------ #

    @given(
        shared_director=_director_st,
        n_sharing=st.integers(min_value=2, max_value=4),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_shared_director_edge_exists_for_sharing_bidders(
        self, shared_director: str, n_sharing: int
    ):
        # Feature: tender-shield, Property 15: Collusion Graph Edge Invariants (SHARED_DIRECTOR)
        #
        # For any two bidders sharing a director name, a SHARED_DIRECTOR edge
        # must exist between their graph nodes.
        tender = _make_tender()
        # All n_sharing bidders share the same director
        sharing_bidders = [
            _make_bidder(f"Addr-{_uid('A')}", shared_director)
            for _ in range(n_sharing)
        ]
        for bidder in sharing_bidders:
            _make_bid(tender, bidder)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)

        for b1, b2 in combinations(sharing_bidders, 2):
            node1 = GraphNode.objects.get(bidder=b1)
            node2 = GraphNode.objects.get(bidder=b2)
            assert _edge_exists(node1, node2, EdgeType.SHARED_DIRECTOR), (
                f"Expected SHARED_DIRECTOR edge between {b1.bidder_id} and "
                f"{b2.bidder_id} sharing director '{shared_director}'"
            )

    @given(n_distinct=st.integers(min_value=2, max_value=4))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_no_shared_director_edge_when_directors_are_distinct(self, n_distinct: int):
        # Feature: tender-shield, Property 15: Collusion Graph Edge Invariants (SHARED_DIRECTOR absent)
        #
        # When all bidders have distinct directors, no SHARED_DIRECTOR edges
        # must be created.
        tender = _make_tender()
        bidders = [
            _make_bidder(f"Addr-{_uid('A')}", f"UniqueDir-{_uid('D')}")
            for _ in range(n_distinct)
        ]
        for bidder in bidders:
            _make_bid(tender, bidder)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)

        node_ids = list(
            GraphNode.objects.filter(bidder__in=bidders).values_list("pk", flat=True)
        )
        shared_dir_count = GraphEdge.objects.filter(
            edge_type=EdgeType.SHARED_DIRECTOR,
            source_node_id__in=node_ids,
        ).count() + GraphEdge.objects.filter(
            edge_type=EdgeType.SHARED_DIRECTOR,
            target_node_id__in=node_ids,
        ).count()
        assert shared_dir_count == 0, (
            f"Expected 0 SHARED_DIRECTOR edges for {n_distinct} bidders with "
            f"distinct directors, got {shared_dir_count}"
        )

    # ------------------------------------------------------------------ #
    # 15c — SHARED_ADDRESS edges                                          #
    # ------------------------------------------------------------------ #

    @given(
        shared_address=_address_st,
        n_sharing=st.integers(min_value=2, max_value=4),
    )
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_shared_address_edge_exists_for_sharing_bidders(
        self, shared_address: str, n_sharing: int
    ):
        # Feature: tender-shield, Property 15: Collusion Graph Edge Invariants (SHARED_ADDRESS)
        #
        # For any two bidders sharing a registered address, a SHARED_ADDRESS
        # edge must exist between their graph nodes.
        tender = _make_tender()
        sharing_bidders = [
            _make_bidder(shared_address, f"Dir-{_uid('D')}")
            for _ in range(n_sharing)
        ]
        for bidder in sharing_bidders:
            _make_bid(tender, bidder)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)

        for b1, b2 in combinations(sharing_bidders, 2):
            node1 = GraphNode.objects.get(bidder=b1)
            node2 = GraphNode.objects.get(bidder=b2)
            assert _edge_exists(node1, node2, EdgeType.SHARED_ADDRESS), (
                f"Expected SHARED_ADDRESS edge between {b1.bidder_id} and "
                f"{b2.bidder_id} sharing address '{shared_address}'"
            )

    @given(n_distinct=st.integers(min_value=2, max_value=4))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_no_shared_address_edge_when_addresses_are_distinct(self, n_distinct: int):
        # Feature: tender-shield, Property 15: Collusion Graph Edge Invariants (SHARED_ADDRESS absent)
        #
        # When all bidders have distinct addresses, no SHARED_ADDRESS edges
        # must be created.
        tender = _make_tender()
        bidders = [
            _make_bidder(f"UniqueAddr-{_uid('A')}", f"Dir-{_uid('D')}")
            for _ in range(n_distinct)
        ]
        for bidder in bidders:
            _make_bid(tender, bidder)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)

        node_ids = list(
            GraphNode.objects.filter(bidder__in=bidders).values_list("pk", flat=True)
        )
        shared_addr_count = GraphEdge.objects.filter(
            edge_type=EdgeType.SHARED_ADDRESS,
            source_node_id__in=node_ids,
        ).count() + GraphEdge.objects.filter(
            edge_type=EdgeType.SHARED_ADDRESS,
            target_node_id__in=node_ids,
        ).count()
        assert shared_addr_count == 0, (
            f"Expected 0 SHARED_ADDRESS edges for {n_distinct} bidders with "
            f"distinct addresses, got {shared_addr_count}"
        )

    # ------------------------------------------------------------------ #
    # 15d — GraphNode upsert invariant                                    #
    # ------------------------------------------------------------------ #

    @given(_bidder_list_st)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_graph_node_created_for_every_bidder(self, specs: List[BidderSpec]):
        # Feature: tender-shield, Property 15: Collusion Graph Edge Invariants (node creation)
        #
        # After update_graph(), a GraphNode must exist for every bidder
        # who submitted a bid on the tender.
        tender = _make_tender()
        bidders = [_make_bidder(s.registered_address, s.director_names) for s in specs]
        for bidder in bidders:
            _make_bid(tender, bidder)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)

        for bidder in bidders:
            assert GraphNode.objects.filter(bidder=bidder).exists(), (
                f"Expected GraphNode for bidder {bidder.bidder_id} after update_graph()"
            )


# ===========================================================================
# Property 16 — Collusion Ring Detection
# ===========================================================================


class CollusionRingDetectionPropertyTest(TestCase):
    """
    Property 16: For any connected component in the collusion graph containing
    3 or more bidder nodes connected by HIGH-severity RedFlag edges, a
    CollusionRing must be created with a unique identifier, and an Alert with
    severity HIGH must be triggered.
    Validates: Requirements 8.4, 8.7
    """

    def _build_ring_scenario(self, size: int):
        """
        Create *size* bidders all co-bidding on a single tender that has a
        HIGH-severity RedFlag.  Returns (tender, bidders).
        """
        tender = _make_tender()
        bidders = [
            _make_bidder(f"RingAddr-{_uid('A')}", f"RingDir-{_uid('D')}")
            for _ in range(size)
        ]
        for bidder in bidders:
            _make_bid(tender, bidder)
        # Raise a HIGH-severity flag on the tender so detect_collusion_rings()
        # includes these CO_BID edges in the adjacency graph.
        _make_high_red_flag(tender, bidders[0])
        return tender, bidders

    # ------------------------------------------------------------------ #
    # 16a — Ring created for components with ≥ 3 nodes                   #
    # ------------------------------------------------------------------ #

    @given(size=st.integers(min_value=3, max_value=10))
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_collusion_ring_created_for_component_with_3_or_more_nodes(self, size: int):
        # Feature: tender-shield, Property 16: Collusion Ring Detection (ring created)
        #
        # For any connected component with ≥ 3 bidder nodes on HIGH-severity
        # RedFlag edges, a CollusionRing must be created.
        tender, bidders = self._build_ring_scenario(size)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        rings = graph.detect_collusion_rings()

        assert len(rings) >= 1, (
            f"Expected at least 1 CollusionRing for {size} co-bidders on a "
            f"HIGH-severity tender, got {len(rings)}"
        )

        # The ring must contain all bidder PKs
        bidder_pks = {b.pk for b in bidders}
        ring_members = set()
        for ring in rings:
            ring_members.update(ring.member_bidder_ids)
        assert bidder_pks.issubset(ring_members), (
            f"Ring members {ring_members} do not include all bidders {bidder_pks}"
        )

    @given(size=st.integers(min_value=3, max_value=10))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_collusion_ring_has_unique_ring_id(self, size: int):
        # Feature: tender-shield, Property 16: Collusion Ring Detection (unique ID)
        #
        # Each CollusionRing must have a non-empty unique ring_id.
        tender, _ = self._build_ring_scenario(size)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        rings = graph.detect_collusion_rings()

        ring_ids = [r.ring_id for r in rings]
        assert all(rid for rid in ring_ids), (
            "All CollusionRing ring_id values must be non-empty"
        )
        assert len(ring_ids) == len(set(ring_ids)), (
            f"CollusionRing ring_ids must be unique, got duplicates: {ring_ids}"
        )

    @given(size=st.integers(min_value=3, max_value=10))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_collusion_ring_member_count_matches_member_list(self, size: int):
        # Feature: tender-shield, Property 16: Collusion Ring Detection (member_count)
        #
        # ring.member_count must equal len(ring.member_bidder_ids).
        tender, _ = self._build_ring_scenario(size)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        rings = graph.detect_collusion_rings()

        for ring in rings:
            assert ring.member_count == len(ring.member_bidder_ids), (
                f"ring.member_count={ring.member_count} does not match "
                f"len(member_bidder_ids)={len(ring.member_bidder_ids)}"
            )

    @given(size=st.integers(min_value=3, max_value=10))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_detect_collusion_rings_is_idempotent(self, size: int):
        # Feature: tender-shield, Property 16: Collusion Ring Detection (idempotent)
        #
        # Calling detect_collusion_rings() twice must not create duplicate rings.
        tender, _ = self._build_ring_scenario(size)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        rings_first = graph.detect_collusion_rings()
        rings_second = graph.detect_collusion_rings()

        # The same ring objects should be returned (no duplicates created)
        ring_ids_first = {r.ring_id for r in rings_first}
        ring_ids_second = {r.ring_id for r in rings_second}
        assert ring_ids_first == ring_ids_second, (
            f"detect_collusion_rings() is not idempotent: "
            f"first={ring_ids_first}, second={ring_ids_second}"
        )
        # DB count must not grow
        db_count = CollusionRing.objects.filter(ring_id__in=ring_ids_first).count()
        assert db_count == len(ring_ids_first), (
            f"Duplicate CollusionRing rows created: db_count={db_count}, "
            f"expected={len(ring_ids_first)}"
        )

    # ------------------------------------------------------------------ #
    # 16b — No ring for components with < 3 nodes                        #
    # ------------------------------------------------------------------ #

    @given(size=st.integers(min_value=1, max_value=2))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_no_collusion_ring_for_component_with_fewer_than_3_nodes(self, size: int):
        # Feature: tender-shield, Property 16: Collusion Ring Detection (below threshold)
        #
        # A connected component with fewer than 3 nodes must NOT produce a
        # CollusionRing.
        tender, bidders = self._build_ring_scenario(size)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        rings = graph.detect_collusion_rings()

        bidder_pks = {b.pk for b in bidders}
        # No ring should contain only these bidders as its sole members
        for ring in rings:
            ring_members = set(ring.member_bidder_ids)
            # If the ring is a strict subset of our bidders, that's a violation
            if ring_members.issubset(bidder_pks) and ring_members == bidder_pks:
                assert False, (
                    f"CollusionRing created for only {size} bidder(s) — "
                    f"threshold is 3. Ring: {ring.ring_id}, members: {ring_members}"
                )

    # ------------------------------------------------------------------ #
    # 16c — Alert triggered for new rings (Requirement 8.7)              #
    # ------------------------------------------------------------------ #

    @given(size=st.integers(min_value=3, max_value=6))
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_alert_triggered_for_new_collusion_ring(self, size: int):
        # Feature: tender-shield, Property 16: Collusion Ring Detection (alert triggered)
        #
        # When a new CollusionRing is detected, Alert records must be created
        # for all AUDITOR and ADMIN users with alert_type COLLUSION_RING.
        # Create at least one recipient user so alerts can be generated.
        auditor = _make_user(UserRole.AUDITOR)

        tender, bidders = self._build_ring_scenario(size)

        # Give the tender a FraudRiskScore so _trigger_ring_alerts can find it
        from scoring.models import FraudRiskScore
        FraudRiskScore.objects.create(
            tender=tender,
            score=85,
            ml_anomaly_score=None,
            ml_collusion_score=None,
            red_flag_contribution=50,
            model_version="test-1.0",
            weight_config={},
        )

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        rings = graph.detect_collusion_rings()

        assume(len(rings) >= 1)

        # Alerts of type COLLUSION_RING must exist for the auditor
        collusion_alerts = Alert.objects.filter(
            user=auditor,
            alert_type=AlertType.COLLUSION_RING,
        )
        assert collusion_alerts.exists(), (
            f"Expected COLLUSION_RING Alert for auditor after ring detection "
            f"(size={size}), but none found"
        )

    @given(size=st.integers(min_value=3, max_value=6))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_alert_not_duplicated_on_second_detect_call(self, size: int):
        # Feature: tender-shield, Property 16: Collusion Ring Detection (no duplicate alerts)
        #
        # Calling detect_collusion_rings() a second time for the same ring
        # must not create additional Alert records.
        auditor = _make_user(UserRole.AUDITOR)

        tender, _ = self._build_ring_scenario(size)

        from scoring.models import FraudRiskScore
        FraudRiskScore.objects.create(
            tender=tender,
            score=85,
            ml_anomaly_score=None,
            ml_collusion_score=None,
            red_flag_contribution=50,
            model_version="test-1.0",
            weight_config={},
        )

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        graph.detect_collusion_rings()

        count_after_first = Alert.objects.filter(
            user=auditor,
            alert_type=AlertType.COLLUSION_RING,
        ).count()

        # Second call — ring already exists, no new alerts should be created
        graph.detect_collusion_rings()

        count_after_second = Alert.objects.filter(
            user=auditor,
            alert_type=AlertType.COLLUSION_RING,
        ).count()

        assert count_after_second == count_after_first, (
            f"Duplicate COLLUSION_RING alerts created on second detect call: "
            f"first={count_after_first}, second={count_after_second}"
        )

    # ------------------------------------------------------------------ #
    # 16d — No ring when no HIGH-severity flags exist                     #
    # ------------------------------------------------------------------ #

    @given(size=st.integers(min_value=3, max_value=6))
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_no_ring_when_no_high_severity_flags(self, size: int):
        # Feature: tender-shield, Property 16: Collusion Ring Detection (no HIGH flags)
        #
        # When no HIGH-severity RedFlags exist, detect_collusion_rings() must
        # return an empty list regardless of graph size.
        tender = _make_tender()
        bidders = [
            _make_bidder(f"NoFlagAddr-{_uid('A')}", f"NoFlagDir-{_uid('D')}")
            for _ in range(size)
        ]
        for bidder in bidders:
            _make_bid(tender, bidder)
        # Deliberately do NOT create any HIGH-severity RedFlags

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        rings = graph.detect_collusion_rings()

        bidder_pks = {b.pk for b in bidders}
        for ring in rings:
            ring_members = set(ring.member_bidder_ids)
            assert not ring_members.issubset(bidder_pks), (
                f"CollusionRing {ring.ring_id} created for bidders with no "
                f"HIGH-severity flags: members={ring_members}"
            )
