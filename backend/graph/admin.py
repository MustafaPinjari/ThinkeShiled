from django.contrib import admin
from graph.models import CollusionRing, GraphEdge, GraphNode


@admin.register(CollusionRing)
class CollusionRingAdmin(admin.ModelAdmin):
    list_display = ["ring_id", "member_count", "detected_at", "is_active"]
    list_filter = ["is_active"]
    readonly_fields = ["ring_id", "detected_at"]


@admin.register(GraphNode)
class GraphNodeAdmin(admin.ModelAdmin):
    list_display = ["bidder", "updated_at"]


@admin.register(GraphEdge)
class GraphEdgeAdmin(admin.ModelAdmin):
    list_display = ["source_node", "target_node", "edge_type", "tender", "created_at"]
    list_filter = ["edge_type"]
