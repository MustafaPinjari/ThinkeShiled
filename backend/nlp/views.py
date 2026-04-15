from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from authentication.permissions import IsAuditorOrAdmin
from nlp.models import SpecAnalysisResult
from nlp.serializers import SpecAnalysisResultSerializer
from tenders.models import Tender


class TenderSpecAnalysisView(APIView):
    """GET /api/v1/tenders/{id}/spec-analysis/ — latest NLP spec analysis result."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, pk):
        try:
            tender = Tender.objects.get(pk=pk)
        except Tender.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        analysis = (
            SpecAnalysisResult.objects.filter(tender=tender)
            .order_by("-analyzed_at")
            .first()
        )
        if analysis is None:
            return Response(
                {"detail": "No spec analysis found for this tender."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(SpecAnalysisResultSerializer(analysis).data)
