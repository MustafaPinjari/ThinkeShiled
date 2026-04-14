from django.db import models
from django.utils import timezone


class EdgeType(models.TextChoices):
    CO_BID = "CO_BID", "Co-Bid"
    SHARED_DIRECTOR = "SHARED_DIRECTOR", "Shared Director"
    SHARED_ADDRESS = "SHARED_ADDRESS", "Shared Address"


class CollusionRing(models.Model):
    ring_id = models.CharField(max_length=255, unique=True)
    member_bidder_ids = models.JSONField(default=list)
    member_count = models.PositiveIntegerField(default=0)
    detected_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "graph_collusionring"
        indexes = [
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"CollusionRing {self.ring_id} ({self.member_count} members)"


class GraphNode(models.Model):
    bidder = models.OneToOneField(
        "bids.Bidder", on_delete=models.CASCADE, related_name="graph_node"
    )
    metadata = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "graph_graphnode"

    def __str__(self):
        return f"Node for {self.bidder}"


class GraphEdge(models.Model):
    source_node = models.ForeignKey(
        GraphNode, on_delete=models.CASCADE, related_name="outgoing_edges"
    )
    target_node = models.ForeignKey(
        GraphNode, on_delete=models.CASCADE, related_name="incoming_edges"
    )
    edge_type = models.CharField(max_length=20, choices=EdgeType.choices)
    tender = models.ForeignKey(
        "tenders.Tender",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="graph_edges",
    )
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "graph_graphedge"
        indexes = [
            models.Index(fields=["edge_type"]),
            models.Index(fields=["source_node", "target_node", "edge_type"]),
        ]

    def __str__(self):
        return f"{self.source_node} --[{self.edge_type}]--> {self.target_node}"
