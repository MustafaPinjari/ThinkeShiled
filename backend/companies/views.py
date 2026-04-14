from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from authentication.permissions import IsAuditorOrAdmin
from bids.models import Bid, Bidder
from companies.models import CompanyProfile
from companies.serializers import CompanyProfileSerializer
from detection.models import RedFlag
from tenders.models import Tender


class CompanyPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ---------------------------------------------------------------------------
# 14.3 — List and detail
# ---------------------------------------------------------------------------

class CompanyListView(APIView):
    """GET /api/v1/companies/ — paginated list of company profiles."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request):
        qs = (
            CompanyProfile.objects.select_related("bidder", "collusion_ring")
            .order_by("-highest_fraud_risk_score", "-active_red_flag_count")
        )

        # Optional filters
        risk_status = request.query_params.get("risk_status")
        if risk_status:
            qs = qs.filter(risk_status=risk_status)

        bidder_name = request.query_params.get("bidder_name")
        if bidder_name:
            qs = qs.filter(bidder__bidder_name__icontains=bidder_name)

        paginator = CompanyPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = CompanyProfileSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class CompanyDetailView(APIView):
    """GET /api/v1/companies/{id}/ — company profile detail."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, pk):
        try:
            profile = CompanyProfile.objects.select_related(
                "bidder", "collusion_ring"
            ).get(pk=pk)
        except CompanyProfile.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(CompanyProfileSerializer(profile).data)


# ---------------------------------------------------------------------------
# 14.4 — Sub-resource views
# ---------------------------------------------------------------------------

class CompanyTendersView(APIView):
    """GET /api/v1/companies/{id}/tenders/ — tenders the company bid on."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, pk):
        try:
            profile = CompanyProfile.objects.select_related("bidder").get(pk=pk)
        except CompanyProfile.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        tender_ids = (
            Bid.objects.filter(bidder=profile.bidder)
            .values_list("tender_id", flat=True)
            .distinct()
        )
        tenders = Tender.objects.filter(pk__in=tender_ids).order_by("-submission_deadline")

        paginator = CompanyPagination()
        page = paginator.paginate_queryset(tenders, request)
        data = [
            {
                "id": t.id,
                "tender_id": t.tender_id,
                "title": t.title,
                "category": t.category,
                "estimated_value": str(t.estimated_value),
                "currency": t.currency,
                "submission_deadline": t.submission_deadline,
                "status": t.status,
            }
            for t in page
        ]
        return paginator.get_paginated_response(data)


class CompanyRedFlagsView(APIView):
    """GET /api/v1/companies/{id}/red-flags/ — red flags linked to the company."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, pk):
        try:
            profile = CompanyProfile.objects.select_related("bidder").get(pk=pk)
        except CompanyProfile.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        flags = (
            RedFlag.objects.filter(bidder=profile.bidder)
            .select_related("tender")
            .order_by("-raised_at")
        )

        paginator = CompanyPagination()
        page = paginator.paginate_queryset(flags, request)
        data = [
            {
                "id": f.id,
                "tender_id": f.tender.tender_id,
                "flag_type": f.flag_type,
                "severity": f.severity,
                "rule_version": f.rule_version,
                "trigger_data": f.trigger_data,
                "is_active": f.is_active,
                "raised_at": f.raised_at,
                "cleared_at": f.cleared_at,
            }
            for f in page
        ]
        return paginator.get_paginated_response(data)
