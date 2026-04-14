from django.db import IntegrityError
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditLog, EventType
from authentication.permissions import IsAdminRole, IsAuditorOrAdmin
from bids.models import Bid
from bids.serializers import BidSerializer, BidReadSerializer
from bids.tasks import (
    evaluate_rules_task,
    compute_score_task,
    score_ml_task,
    update_company_profile_task,
    update_graph_task,
)
from tenders.models import Tender


def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _enqueue_pipeline(tender_id: int, bidder_id: int) -> None:
    """Enqueue the full post-ingestion fraud detection pipeline."""
    evaluate_rules_task.delay(tender_id)
    compute_score_task.delay(tender_id)
    score_ml_task.delay(tender_id)
    update_company_profile_task.delay(bidder_id)
    update_graph_task.delay(tender_id)


# ---------------------------------------------------------------------------
# 7.2 — Single bid creation
# ---------------------------------------------------------------------------

class BidCreateView(APIView):
    """POST /api/v1/bids/ — create a single bid (ADMIN only)."""

    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = BidSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Bid validation failed.",
                        "details": serializer.errors,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            bid, bidder, _ = serializer.create_bid()
        except IntegrityError:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": f"A bid with bid_id '{request.data.get('bid_id')}' already exists.",
                        "details": {"bid_id": ["Duplicate bid_id."]},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        AuditLog.objects.create(
            event_type=EventType.BID_INGESTED,
            user=request.user,
            affected_entity_type="Bid",
            affected_entity_id=bid.bid_id,
            data_snapshot={
                "bid_id": bid.bid_id,
                "tender_id": bid.tender.tender_id,
                "bidder_id": bidder.bidder_id,
                "bid_amount": str(bid.bid_amount),
                "submission_timestamp": bid.submission_timestamp.isoformat(),
            },
            ip_address=_get_client_ip(request),
        )

        _enqueue_pipeline(bid.tender.pk, bidder.pk)

        return Response(BidReadSerializer(bid).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# 7.3 — Bulk bid ingestion
# ---------------------------------------------------------------------------

class BidBulkCreateView(APIView):
    """POST /api/v1/bids/bulk/ — ingest multiple bids (ADMIN only)."""

    permission_classes = [IsAdminRole]

    def post(self, request):
        if not isinstance(request.data, list):
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Request body must be a JSON array of bid objects.",
                        "details": {},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        accepted = []
        rejected = []
        ip = _get_client_ip(request)

        for idx, item in enumerate(request.data):
            serializer = BidSerializer(data=item)
            if not serializer.is_valid():
                rejected.append({"index": idx, "bid_id": item.get("bid_id", ""), "errors": serializer.errors})
                continue

            try:
                bid, bidder, _ = serializer.create_bid()
            except IntegrityError:
                rejected.append({
                    "index": idx,
                    "bid_id": item.get("bid_id", ""),
                    "errors": {"bid_id": ["Duplicate bid_id."]},
                })
                continue

            AuditLog.objects.create(
                event_type=EventType.BID_INGESTED,
                user=request.user,
                affected_entity_type="Bid",
                affected_entity_id=bid.bid_id,
                data_snapshot={
                    "bid_id": bid.bid_id,
                    "tender_id": bid.tender.tender_id,
                    "bidder_id": bidder.bidder_id,
                    "bid_amount": str(bid.bid_amount),
                    "submission_timestamp": bid.submission_timestamp.isoformat(),
                },
                ip_address=ip,
            )

            _enqueue_pipeline(bid.tender.pk, bidder.pk)
            accepted.append(BidReadSerializer(bid).data)

        return Response(
            {
                "accepted": len(accepted),
                "rejected": len(rejected),
                "accepted_bids": accepted,
                "rejected_bids": rejected,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# 7.4 — List bids for a tender
# ---------------------------------------------------------------------------

class BidPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class BidListView(APIView):
    """GET /api/v1/bids/?tender_id={id} — list bids for a tender (AUDITOR, ADMIN)."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request):
        tender_id = request.query_params.get("tender_id")
        if not tender_id:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "tender_id query parameter is required.",
                        "details": {},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            tender = Tender.objects.get(tender_id=tender_id)
        except Tender.DoesNotExist:
            return Response({"detail": "Tender not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = Bid.objects.filter(tender=tender).select_related("bidder").order_by("submission_timestamp")
        paginator = BidPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = BidReadSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ---------------------------------------------------------------------------
# Combined root view: GET = list, POST = create single
# ---------------------------------------------------------------------------

class BidRootView(APIView):
    """
    GET  /api/v1/bids/?tender_id={id} — list bids (AUDITOR, ADMIN)
    POST /api/v1/bids/                — create single bid (ADMIN only)
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminRole()]
        return [IsAuditorOrAdmin()]

    def get(self, request):
        return BidListView().get(request)

    def post(self, request):
        return BidCreateView().post(request)
