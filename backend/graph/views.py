"""
Graph API views.

GET /api/v1/graph/                  — full graph data (nodes + edges)
GET /api/v1/graph/?edge_type=CO_BID — filtered by edge type
GET /api/v1/graph/rings/            — list all detected collusion rings
GET /api/v1/graph/rings/{ring_id}/  — collusion ring detail
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from authentication.permissions import IsAuditorOrAdmin
from graph.collusion_graph import CollusionGraph
from graph.models import CollusionRing, EdgeType
from graph.serializers import CollusionRingSerializer


class GraphDataView(APIView):
    """
    GET /api/v1/graph/
    Returns {nodes, edges} for the full collusion graph.
    Supports ?edge_type= filter (CO_BID | SHARED_DIRECTOR | SHARED_ADDRESS).
    """

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request):
        edge_type = request.query_params.get("edge_type")

        # Validate edge_type if provided
        if edge_type and edge_type not in EdgeType.values:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": f"Invalid edge_type. Choose from: {EdgeType.values}"}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        graph = CollusionGraph()
        data = graph.get_graph_data(edge_type=edge_type)
        return Response(data)


class CollusionRingListView(APIView):
    """
    GET /api/v1/graph/rings/
    Returns all detected collusion rings.
    """

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request):
        rings = CollusionRing.objects.filter(is_active=True).order_by("-detected_at")
        serializer = CollusionRingSerializer(rings, many=True)
        return Response(serializer.data)


class CollusionRingDetailView(APIView):
    """
    GET /api/v1/graph/rings/{ring_id}/
    Returns detail for a single collusion ring.
    """

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, ring_id: str):
        try:
            ring = CollusionRing.objects.get(ring_id=ring_id)
        except CollusionRing.DoesNotExist:
            return Response(
                {"error": {"code": "NOT_FOUND", "message": "Collusion ring not found."}},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = CollusionRingSerializer(ring)
        return Response(serializer.data)
