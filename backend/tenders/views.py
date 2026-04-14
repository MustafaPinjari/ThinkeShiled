import csv
import io

from django.db import IntegrityError
from django.db.models import OuterRef, Subquery, Count, Q
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditLog, EventType
from authentication.permissions import IsAdminRole, IsAuditorOrAdmin
from detection.models import RedFlag
from scoring.models import FraudRiskScore
from tenders.models import Tender
from tenders.serializers import TenderSerializer, TenderListSerializer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MANDATORY_CSV_FIELDS = [
    "tender_id",
    "title",
    "category",
    "estimated_value",
    "currency",
    "submission_deadline",
    "buyer_id",
    "buyer_name",
]


def _get_client_ip(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded:
        return x_forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _validation_error_response(message, details=None):
    return Response(
        {
            "error": {
                "code": "VALIDATION_ERROR",
                "message": message,
                "details": details or {},
            }
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


# ---------------------------------------------------------------------------
# 6.2 — Single tender creation
# ---------------------------------------------------------------------------

class TenderCreateView(APIView):
    """POST /api/v1/tenders/ — create a single tender (ADMIN only)."""

    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = TenderSerializer(data=request.data)
        if not serializer.is_valid():
            return _validation_error_response(
                "Tender validation failed.",
                serializer.errors,
            )

        try:
            tender = serializer.save()
        except IntegrityError:
            return _validation_error_response(
                f"A tender with tender_id '{request.data.get('tender_id')}' already exists.",
                {"tender_id": ["Duplicate tender_id."]},
            )

        # Write audit log
        AuditLog.objects.create(
            event_type=EventType.TENDER_INGESTED,
            user=request.user,
            affected_entity_type="Tender",
            affected_entity_id=tender.tender_id,
            data_snapshot=TenderSerializer(tender).data,
            ip_address=_get_client_ip(request),
        )

        return Response(TenderSerializer(tender).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# 6.3 — CSV batch upload
# ---------------------------------------------------------------------------

class TenderCSVUploadView(APIView):
    """POST /api/v1/tenders/upload/ — batch CSV upload (ADMIN only)."""

    permission_classes = [IsAdminRole]

    def post(self, request):
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return _validation_error_response("No file provided.", {"file": ["This field is required."]})

        try:
            text = uploaded_file.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            return _validation_error_response("File must be UTF-8 encoded.")

        reader = csv.DictReader(io.StringIO(text))

        accepted_tenders = []
        rejected_rows = []

        # Collect all tender_ids in this batch to detect intra-batch duplicates
        seen_in_batch = {}

        rows = list(reader)

        # Bulk-check existing tender_ids in DB
        candidate_ids = [row.get("tender_id", "").strip() for row in rows if row.get("tender_id", "").strip()]
        existing_ids = set(
            Tender.objects.filter(tender_id__in=candidate_ids).values_list("tender_id", flat=True)
        )

        for row_num, row in enumerate(rows, start=2):  # row 1 = header
            tender_id = row.get("tender_id", "").strip()

            # Check mandatory fields
            missing = [f for f in MANDATORY_CSV_FIELDS if not row.get(f, "").strip()]
            if missing:
                rejected_rows.append({
                    "row": row_num,
                    "tender_id": tender_id or "",
                    "reason": f"Missing mandatory fields: {', '.join(missing)}",
                })
                continue

            # Check DB duplicate
            if tender_id in existing_ids:
                rejected_rows.append({
                    "row": row_num,
                    "tender_id": tender_id,
                    "reason": f"Duplicate tender_id '{tender_id}' already exists in database.",
                })
                continue

            # Check intra-batch duplicate
            if tender_id in seen_in_batch:
                rejected_rows.append({
                    "row": row_num,
                    "tender_id": tender_id,
                    "reason": f"Duplicate tender_id '{tender_id}' appears earlier in this batch (row {seen_in_batch[tender_id]}).",
                })
                continue

            seen_in_batch[tender_id] = row_num

            # Validate via serializer
            data = {
                "tender_id": row.get("tender_id", "").strip(),
                "title": row.get("title", "").strip(),
                "category": row.get("category", "").strip(),
                "estimated_value": row.get("estimated_value", "").strip(),
                "currency": row.get("currency", "").strip(),
                "submission_deadline": row.get("submission_deadline", "").strip(),
                "buyer_id": row.get("buyer_id", "").strip(),
                "buyer_name": row.get("buyer_name", "").strip(),
            }
            if row.get("status", "").strip():
                data["status"] = row["status"].strip()
            if row.get("publication_date", "").strip():
                data["publication_date"] = row["publication_date"].strip()

            serializer = TenderSerializer(data=data)
            if not serializer.is_valid():
                rejected_rows.append({
                    "row": row_num,
                    "tender_id": tender_id,
                    "reason": str(serializer.errors),
                })
                continue

            accepted_tenders.append(Tender(**{
                k: v for k, v in serializer.validated_data.items()
            }))

        # Bulk create in batches of 1000
        created_count = 0
        batch_size = 1000
        for i in range(0, len(accepted_tenders), batch_size):
            batch = accepted_tenders[i: i + batch_size]
            Tender.objects.bulk_create(batch, ignore_conflicts=False)
            created_count += len(batch)

        return Response(
            {
                "accepted": created_count,
                "rejected": len(rejected_rows),
                "rejected_rows": rejected_rows,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Combined root view: GET = list, POST = create single
# ---------------------------------------------------------------------------

class TenderRootView(APIView):
    """
    GET  /api/v1/tenders/ — paginated list (AUDITOR or ADMIN)
    POST /api/v1/tenders/ — create single tender (ADMIN only)
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminRole()]
        return [IsAuditorOrAdmin()]

    def get(self, request):
        return TenderListView().get(request)

    def post(self, request):
        return TenderCreateView().post(request)


# ---------------------------------------------------------------------------
# 6.5 — Paginated list with filters
# ---------------------------------------------------------------------------

class TenderPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


VALID_ORDERINGS = {
    "score": "latest_score",
    "-score": "-latest_score",
    "deadline": "submission_deadline",
    "-deadline": "-submission_deadline",
    "category": "category",
    "buyer_name": "buyer_name",
}


class TenderListView(APIView):
    """GET /api/v1/tenders/ — paginated list with filters (AUDITOR or ADMIN)."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request):
        # Latest score subquery
        latest_score_sq = (
            FraudRiskScore.objects.filter(tender=OuterRef("pk"))
            .order_by("-computed_at")
            .values("score")[:1]
        )

        qs = Tender.objects.annotate(
            latest_score=Subquery(latest_score_sq),
            active_red_flag_count=Count(
                "red_flags", filter=Q(red_flags__is_active=True)
            ),
        ).only(
            "id", "tender_id", "title", "category", "estimated_value",
            "currency", "submission_deadline", "buyer_id", "buyer_name",
            "status", "created_at",
        )

        # Filters
        score_min = request.query_params.get("score_min")
        score_max = request.query_params.get("score_max")
        category = request.query_params.get("category")
        buyer_name = request.query_params.get("buyer_name")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        flag_type = request.query_params.get("flag_type")
        ordering_param = request.query_params.get("ordering", "-score")

        if score_min is not None:
            try:
                qs = qs.filter(latest_score__gte=int(score_min))
            except ValueError:
                pass

        if score_max is not None:
            try:
                qs = qs.filter(latest_score__lte=int(score_max))
            except ValueError:
                pass

        if category:
            qs = qs.filter(category__icontains=category)

        if buyer_name:
            qs = qs.filter(buyer_name__icontains=buyer_name)

        if date_from:
            qs = qs.filter(submission_deadline__date__gte=date_from)

        if date_to:
            qs = qs.filter(submission_deadline__date__lte=date_to)

        if flag_type:
            qs = qs.filter(
                red_flags__flag_type=flag_type,
                red_flags__is_active=True,
            ).distinct()

        # Ordering
        order_field = VALID_ORDERINGS.get(ordering_param, "-latest_score")
        qs = qs.order_by(order_field)

        paginator = TenderPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = TenderListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


# ---------------------------------------------------------------------------
# 6.6 — Detail and sub-resource endpoints
# ---------------------------------------------------------------------------

class TenderDetailView(APIView):
    """GET /api/v1/tenders/{id}/ — full tender detail (AUDITOR or ADMIN)."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, pk):
        try:
            tender = Tender.objects.get(pk=pk)
        except Tender.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(TenderSerializer(tender).data)


class TenderScoreView(APIView):
    """GET /api/v1/tenders/{id}/score/ — latest FraudRiskScore."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, pk):
        try:
            tender = Tender.objects.get(pk=pk)
        except Tender.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        score_obj = (
            FraudRiskScore.objects.filter(tender=tender).order_by("-computed_at").first()
        )
        if score_obj is None:
            return Response({"score": None})

        return Response({
            "score": score_obj.score,
            "ml_anomaly_score": score_obj.ml_anomaly_score,
            "ml_collusion_score": score_obj.ml_collusion_score,
            "red_flag_contribution": score_obj.red_flag_contribution,
            "model_version": score_obj.model_version,
            "weight_config": score_obj.weight_config,
            "computed_at": score_obj.computed_at,
        })


class TenderExplanationView(APIView):
    """GET /api/v1/tenders/{id}/explanation/ — XAI explanation (SHAP + red flags)."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, pk):
        try:
            tender = Tender.objects.get(pk=pk)
        except Tender.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        model_version = request.query_params.get("model_version", "")

        from xai.explainer import XAIExplainer
        explainer = XAIExplainer()
        explanation = explainer.explain(tender_id=tender.pk, model_version=model_version)

        if "error" in explanation:
            return Response({"detail": explanation["error"]}, status=status.HTTP_404_NOT_FOUND)

        return Response(explanation)


class TenderRedFlagsView(APIView):
    """GET /api/v1/tenders/{id}/red-flags/ — all active RedFlags for the tender."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, pk):
        try:
            tender = Tender.objects.get(pk=pk)
        except Tender.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        flags = RedFlag.objects.filter(tender=tender, is_active=True).order_by("-raised_at")
        data = [
            {
                "id": f.id,
                "flag_type": f.flag_type,
                "severity": f.severity,
                "rule_version": f.rule_version,
                "trigger_data": f.trigger_data,
                "is_active": f.is_active,
                "raised_at": f.raised_at,
                "cleared_at": f.cleared_at,
            }
            for f in flags
        ]
        return Response(data)


class TenderRescoreView(APIView):
    """POST /api/v1/tenders/{id}/rescore/ — trigger manual ML rescore (ADMIN only)."""

    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        try:
            tender = Tender.objects.get(pk=pk)
        except Tender.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        from celery import current_app
        task = current_app.send_task("ml_worker.score_tender", args=[tender.id])

        AuditLog.objects.create(
            event_type=EventType.SCORE_COMPUTED,
            user=request.user,
            affected_entity_type="Tender",
            affected_entity_id=tender.tender_id,
            data_snapshot={"action": "manual_rescore", "task_id": task.id},
            ip_address=_get_client_ip(request),
        )

        return Response(
            {"detail": "Rescore task enqueued.", "task_id": task.id},
            status=status.HTTP_202_ACCEPTED,
        )


class TenderStatusChangeView(APIView):
    """PATCH /api/v1/tenders/{id}/status/ — user-initiated status change (ADMIN only)."""

    permission_classes = [IsAdminRole]

    VALID_STATUSES = {"open", "closed", "awarded", "cancelled"}

    def patch(self, request, pk):
        try:
            tender = Tender.objects.get(pk=pk)
        except Tender.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        new_status = request.data.get("status", "")
        if not new_status:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "status field is required.",
                        "details": {},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if new_status not in self.VALID_STATUSES:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": f"Invalid status. Must be one of: {', '.join(sorted(self.VALID_STATUSES))}.",
                        "details": {},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        old_status = tender.status
        tender.status = new_status
        tender.save(update_fields=["status", "updated_at"])

        AuditLog.objects.create(
            event_type=EventType.STATUS_CHANGED,
            user=request.user,
            affected_entity_type="Tender",
            affected_entity_id=tender.tender_id,
            data_snapshot={
                "tender_id": tender.tender_id,
                "old_status": old_status,
                "new_status": new_status,
            },
            ip_address=_get_client_ip(request),
        )

        return Response(
            {"detail": "Status updated.", "status": new_status},
            status=status.HTTP_200_OK,
        )


class TenderScoreHistoryPagination(PageNumberPagination):
    page_size = 20


class TenderScoreHistoryView(APIView):
    """GET /api/v1/tenders/{id}/score-history/ — all FraudRiskScore rows, paginated."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request, pk):
        try:
            tender = Tender.objects.get(pk=pk)
        except Tender.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        qs = FraudRiskScore.objects.filter(tender=tender).order_by("-computed_at")
        paginator = TenderScoreHistoryPagination()
        page = paginator.paginate_queryset(qs, request)
        data = [
            {
                "id": s.id,
                "score": s.score,
                "ml_anomaly_score": s.ml_anomaly_score,
                "ml_collusion_score": s.ml_collusion_score,
                "red_flag_contribution": s.red_flag_contribution,
                "model_version": s.model_version,
                "weight_config": s.weight_config,
                "computed_at": s.computed_at,
            }
            for s in page
        ]
        return paginator.get_paginated_response(data)


# ---------------------------------------------------------------------------
# Dashboard stats endpoint
# ---------------------------------------------------------------------------

class TenderStatsView(APIView):
    """GET /api/v1/tenders/stats/ — summary counts for the dashboard."""

    permission_classes = [IsAuditorOrAdmin]

    def get(self, request):
        from graph.models import CollusionRing

        latest_score_sq = (
            FraudRiskScore.objects.filter(tender=OuterRef("pk"))
            .order_by("-computed_at")
            .values("score")[:1]
        )

        qs = Tender.objects.annotate(latest_score=Subquery(latest_score_sq))

        total_tenders = qs.count()
        high_risk_count = qs.filter(latest_score__gte=70).count()
        high_flag_count = (
            Tender.objects.filter(
                red_flags__is_active=True,
                red_flags__severity="HIGH",
            )
            .distinct()
            .count()
        )
        collusion_ring_count = CollusionRing.objects.filter(is_active=True).count()

        return Response(
            {
                "total_tenders": total_tenders,
                "high_risk_count": high_risk_count,
                "high_flag_count": high_flag_count,
                "collusion_ring_count": collusion_ring_count,
            }
        )
