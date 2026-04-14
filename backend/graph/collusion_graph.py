"""
CollusionGraph — builds and maintains a graph of bidder relationships.

Nodes  : one GraphNode per Bidder
Edges  : CO_BID (co-bidding on same tender)
         SHARED_DIRECTOR (share a director name)
         SHARED_ADDRESS  (share a registered address)

Collusion rings are connected components with ≥ 3 nodes linked by
HIGH-severity RedFlag edges.  Each new ring triggers an Alert.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from itertools import combinations
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class CollusionGraph:
    """
    Builds and queries the collusion network graph.

    Usage (Celery task):
        graph = CollusionGraph()
        graph.update_graph(tender_id)
        rings = graph.detect_collusion_rings()
    """

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def update_graph(self, tender_id: int) -> None:
        """
        Upsert GraphNodes for every bidder on *tender_id*, then create:
          - CO_BID edges for every pair of bidders on the same tender
          - SHARED_DIRECTOR edges for bidder pairs sharing a director name
          - SHARED_ADDRESS edges for bidder pairs sharing a registered address

        Designed to complete within 30 seconds (Requirement 8.6).
        """
        from bids.models import Bid, Bidder
        from graph.models import GraphNode, GraphEdge, EdgeType

        bids = list(
            Bid.objects.filter(tender_id=tender_id)
            .select_related("bidder")
        )
        if not bids:
            logger.info("CollusionGraph.update_graph: no bids for tender %s", tender_id)
            return

        bidders = [bid.bidder for bid in bids]

        with transaction.atomic():
            # 1. Upsert GraphNodes
            nodes: dict[int, GraphNode] = {}
            for bidder in bidders:
                node, _ = GraphNode.objects.get_or_create(
                    bidder=bidder,
                    defaults={"metadata": {"bidder_name": bidder.bidder_name}},
                )
                # Refresh metadata
                node.metadata = {"bidder_name": bidder.bidder_name}
                node.save(update_fields=["metadata", "updated_at"])
                nodes[bidder.pk] = node

            # 2. CO_BID edges — every pair of bidders on this tender
            for b1, b2 in combinations(bidders, 2):
                self._upsert_edge(
                    nodes[b1.pk],
                    nodes[b2.pk],
                    EdgeType.CO_BID,
                    tender_id=tender_id,
                    metadata={"tender_id": tender_id},
                )

            # 3. SHARED_DIRECTOR / SHARED_ADDRESS edges across all bidders
            #    that share registry data with any bidder in this tender
            bidder_ids = [b.pk for b in bidders]
            all_bidders = list(
                Bidder.objects.filter(pk__in=bidder_ids)
            )
            self._create_registry_edges(all_bidders, nodes)

        logger.info(
            "CollusionGraph.update_graph: processed tender %s with %d bidders",
            tender_id,
            len(bidders),
        )

    def detect_collusion_rings(self) -> list:
        """
        Find connected components with ≥ 3 nodes connected by HIGH-severity
        RedFlag edges.  Create CollusionRing records for new rings and trigger
        AlertSystem with severity HIGH for each.

        Returns the list of (new or existing) CollusionRing instances.
        """
        from graph.models import GraphNode, GraphEdge, CollusionRing
        from detection.models import RedFlag, Severity

        # Build adjacency from HIGH-severity red flags
        # A pair of bidders is "connected" if they share a tender that has
        # at least one active HIGH-severity red flag.
        high_flag_tender_ids = set(
            RedFlag.objects.filter(
                is_active=True, severity=Severity.HIGH
            ).values_list("tender_id", flat=True)
        )

        if not high_flag_tender_ids:
            return []

        # Collect CO_BID edges on those tenders
        edges = list(
            GraphEdge.objects.filter(
                tender_id__in=high_flag_tender_ids,
                edge_type="CO_BID",
            ).select_related("source_node__bidder", "target_node__bidder")
        )

        # Also include SHARED_DIRECTOR / SHARED_ADDRESS edges whose nodes
        # appear in the high-risk tender set
        node_ids_in_high_tenders = set(
            GraphEdge.objects.filter(
                tender_id__in=high_flag_tender_ids,
            ).values_list("source_node_id", flat=True)
        ) | set(
            GraphEdge.objects.filter(
                tender_id__in=high_flag_tender_ids,
            ).values_list("target_node_id", flat=True)
        )

        registry_edges = list(
            GraphEdge.objects.filter(
                edge_type__in=["SHARED_DIRECTOR", "SHARED_ADDRESS"],
                source_node_id__in=node_ids_in_high_tenders,
            ).select_related("source_node__bidder", "target_node__bidder")
        )

        all_edges = edges + registry_edges

        # Union-Find to identify connected components
        parent: dict[int, int] = {}

        def find(x: int) -> int:
            if parent.get(x, x) != x:
                parent[x] = find(parent[x])
            return parent.get(x, x)

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        for edge in all_edges:
            src = edge.source_node.bidder_id
            tgt = edge.target_node.bidder_id
            union(src, tgt)

        # Group bidder PKs by component root
        component_map: dict[int, set[int]] = defaultdict(set)
        all_node_bidder_ids: set[int] = set()
        for edge in all_edges:
            all_node_bidder_ids.add(edge.source_node.bidder_id)
            all_node_bidder_ids.add(edge.target_node.bidder_id)

        for bidder_pk in all_node_bidder_ids:
            root = find(bidder_pk)
            component_map[root].add(bidder_pk)

        # Filter components with ≥ 3 members
        rings_found = []
        for root, members in component_map.items():
            if len(members) < 3:
                continue
            rings_found.append(self._upsert_collusion_ring(sorted(members)))

        return rings_found

    def get_graph_data(self, edge_type: Optional[str] = None) -> dict:
        """
        Return {nodes, edges} JSON-serialisable dict for frontend rendering.
        Optionally filter edges by *edge_type*.
        """
        from graph.models import GraphNode, GraphEdge
        from companies.models import CompanyProfile

        nodes_qs = GraphNode.objects.select_related("bidder").all()
        edges_qs = GraphEdge.objects.select_related(
            "source_node__bidder", "target_node__bidder"
        )
        if edge_type:
            edges_qs = edges_qs.filter(edge_type=edge_type)

        # Build a quick lookup for risk_status and fraud score
        bidder_ids = list(nodes_qs.values_list("bidder_id", flat=True))
        profiles = {
            p.bidder_id: p
            for p in CompanyProfile.objects.filter(bidder_id__in=bidder_ids)
        }

        nodes = []
        for node in nodes_qs:
            profile = profiles.get(node.bidder_id)
            nodes.append({
                "id": node.pk,
                "bidder_id": node.bidder.bidder_id,
                "label": node.bidder.bidder_name,
                "risk_status": profile.risk_status if profile else "LOW",
                "fraud_score": profile.highest_fraud_risk_score if profile else 0,
            })

        edges = []
        for edge in edges_qs:
            edges.append({
                "id": edge.pk,
                "source": edge.source_node_id,
                "target": edge.target_node_id,
                "type": edge.edge_type,
                "tender_id": edge.tender_id,
            })

        return {"nodes": nodes, "edges": edges}

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    def _upsert_edge(
        self,
        source: "GraphNode",
        target: "GraphNode",
        edge_type: str,
        tender_id: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """Create edge if it doesn't already exist (idempotent)."""
        from graph.models import GraphEdge

        # Normalise direction so (A→B) and (B→A) are treated as the same edge
        src, tgt = (
            (source, target)
            if source.pk <= target.pk
            else (target, source)
        )
        GraphEdge.objects.get_or_create(
            source_node=src,
            target_node=tgt,
            edge_type=edge_type,
            tender_id=tender_id,
            defaults={"metadata": metadata or {}},
        )

    def _create_registry_edges(
        self,
        bidders: list,
        nodes: dict[int, "GraphNode"],
    ) -> None:
        """
        Create SHARED_DIRECTOR and SHARED_ADDRESS edges for bidder pairs
        that share registry data.  Only considers bidders already in *nodes*.
        """
        from graph.models import EdgeType

        for b1, b2 in combinations(bidders, 2):
            if b1.pk not in nodes or b2.pk not in nodes:
                continue

            # SHARED_DIRECTOR
            dirs1 = set(b1.get_director_list())
            dirs2 = set(b2.get_director_list())
            if dirs1 & dirs2:
                self._upsert_edge(
                    nodes[b1.pk],
                    nodes[b2.pk],
                    EdgeType.SHARED_DIRECTOR,
                    metadata={"shared_directors": list(dirs1 & dirs2)},
                )

            # SHARED_ADDRESS
            addr1 = b1.registered_address.strip().lower()
            addr2 = b2.registered_address.strip().lower()
            if addr1 and addr2 and addr1 == addr2:
                self._upsert_edge(
                    nodes[b1.pk],
                    nodes[b2.pk],
                    EdgeType.SHARED_ADDRESS,
                    metadata={"shared_address": b1.registered_address},
                )

    def _upsert_collusion_ring(self, member_bidder_ids: list[int]) -> "CollusionRing":
        """
        Create or retrieve a CollusionRing for the given sorted member list.
        Triggers AlertSystem for newly created rings.
        """
        from graph.models import CollusionRing

        sorted_ids = sorted(member_bidder_ids)

        # Check if a ring with exactly these members already exists
        # Use Python-level comparison to avoid DB-specific JSON contains issues
        existing = None
        for ring in CollusionRing.objects.filter(
            member_count=len(sorted_ids), is_active=True
        ):
            if sorted(ring.member_bidder_ids) == sorted_ids:
                existing = ring
                break

        if existing:
            return existing

        ring = CollusionRing.objects.create(
            ring_id=str(uuid.uuid4()),
            member_bidder_ids=sorted_ids,
            member_count=len(sorted_ids),
            detected_at=timezone.now(),
            is_active=True,
        )

        logger.info(
            "CollusionGraph: new ring %s detected with %d members: %s",
            ring.ring_id,
            ring.member_count,
            member_bidder_ids,
        )

        # Update company profiles for all ring members
        self._flag_ring_members(member_bidder_ids, ring.ring_id)

        # Trigger alerts for each tender associated with ring members
        self._trigger_ring_alerts(member_bidder_ids, ring)

        return ring

    def _flag_ring_members(self, member_bidder_ids: list[int], ring_id: str) -> None:
        """Set HIGH_RISK on all ring members and record the ring FK."""
        from companies.models import CompanyProfile, RiskStatus
        from bids.models import Bidder
        from graph.models import CollusionRing

        try:
            ring_obj = CollusionRing.objects.get(ring_id=ring_id)
        except CollusionRing.DoesNotExist:
            ring_obj = None

        for bidder_pk in member_bidder_ids:
            try:
                bidder = Bidder.objects.get(pk=bidder_pk)
                profile, _ = CompanyProfile.objects.get_or_create(bidder=bidder)
                profile.risk_status = RiskStatus.HIGH_RISK
                if ring_obj is not None:
                    profile.collusion_ring = ring_obj
                profile.save(update_fields=["risk_status", "collusion_ring", "updated_at"])
            except Exception as exc:
                logger.error(
                    "CollusionGraph._flag_ring_members: error for bidder %s: %s",
                    bidder_pk,
                    exc,
                )

    def _trigger_ring_alerts(self, member_bidder_ids: list[int], ring: "CollusionRing") -> None:
        """
        Trigger AlertSystem for each tender associated with ring members.
        Uses the highest-scoring tender as the primary alert target.
        """
        from bids.models import Bid
        from scoring.models import FraudRiskScore
        from alerts.models import Alert, AlertType, DeliveryStatus
        from authentication.models import User, UserRole

        # Find tenders involving ring members
        tender_ids = list(
            Bid.objects.filter(bidder_id__in=member_bidder_ids)
            .values_list("tender_id", flat=True)
            .distinct()
        )
        if not tender_ids:
            return

        # Pick the highest-risk tender
        top_score = (
            FraudRiskScore.objects.filter(tender_id__in=tender_ids)
            .order_by("-score", "-computed_at")
            .first()
        )
        if not top_score:
            return

        tender = top_score.tender
        score_value = top_score.score

        # Collect top 3 red flags
        from detection.models import RedFlag
        top_flags = list(
            RedFlag.objects.filter(tender=tender, is_active=True)
            .order_by("-severity")
            .values("flag_type", "severity", "trigger_data")[:3]
        )

        # Create Alert for all AUDITOR and ADMIN users
        users = User.objects.filter(role__in=[UserRole.AUDITOR, UserRole.ADMIN])
        alerts = [
            Alert(
                tender=tender,
                user=user,
                alert_type=AlertType.COLLUSION_RING,
                fraud_risk_score=score_value,
                top_red_flags=top_flags,
                delivery_status=DeliveryStatus.PENDING,
            )
            for user in users
        ]
        Alert.objects.bulk_create(alerts, ignore_conflicts=True)

        logger.info(
            "CollusionGraph: triggered %d alerts for ring %s on tender %s",
            len(alerts),
            ring.ring_id,
            tender.pk,
        )
