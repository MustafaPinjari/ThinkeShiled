"""
Audit log API views.

Endpoints
---------
GET  /api/v1/audit-log/                        — paginated list (ADMIN only)
POST /api/v1/audit-log/export/                 — enqueue PDF export task
GET  /api/v1/audit-log/export/{task_id}/status/ — poll task status / download URL
"""

from __future__ import annotations

import os
import re

from celery.result import AsyncResult
from django.conf import settings
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.models import AuditLog
from audit.tasks import generate_audit_pdf
from authentication.permissions import IsAdminRole


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------

class AuditLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


# ---------------------------------------------------------------------------
# 17.3 — GET /api/v1/audit-log/
# ---------------------------------------------------------------------------

class AuditLogListView(APIView):
    """
    GET /api/v1/audit-log/ — paginated list of AuditLog entries (ADMIN only).

    Query parameters
    ----------------
    event_type  — filter by event type string
    user_id     — filter by user PK
    date_from   — ISO date "YYYY-MM-DD" (inclusive)
    date_to     — ISO date "YYYY-MM-DD" (inclusive)
    entity_type — filter by affected_entity_type
    page        — page number (default 1)
    page_size   — entries per page (default 50, max 200)
    """

    permission_classes = [IsAdminRole]

    def get(self, request):
        qs = AuditLog.objects.select_related("user").order_by("-timestamp")

        # Optional filters
        event_type = request.query_params.get("event_type")
        user_id = request.query_params.get("user_id")
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")
        entity_type = request.query_params.get("entity_type")

        if event_type:
            qs = qs.filter(event_type=event_type)
        if user_id:
            qs = qs.filter(user_id=user_id)
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)
        if entity_type:
            qs = qs.filter(affected_entity_type=entity_type)

        paginator = AuditLogPagination()
        page = paginator.paginate_queryset(qs, request)

        data = [
            {
                "id": entry.id,
                "event_type": entry.event_type,
                "timestamp": entry.timestamp.isoformat(),
                "user_id": entry.user_id,
                "username": entry.user.username if entry.user else None,
                "affected_entity_type": entry.affected_entity_type,
                "affected_entity_id": entry.affected_entity_id,
                "data_snapshot": entry.data_snapshot,
                "ip_address": entry.ip_address,
            }
            for entry in page
        ]
        return paginator.get_paginated_response(data)


# ---------------------------------------------------------------------------
# 17.4 — POST /api/v1/audit-log/export/
# ---------------------------------------------------------------------------

class AuditLogExportView(APIView):
    """
    POST /api/v1/audit-log/export/ — enqueue a PDF export Celery task.

    Request body
    ------------
    {
        "date_from": "YYYY-MM-DD",
        "date_to":   "YYYY-MM-DD"
    }

    Response 202
    ------------
    { "task_id": "<celery-task-id>", "status": "queued" }
    """

    permission_classes = [IsAdminRole]

    def post(self, request):
        date_from = request.data.get("date_from", "")
        date_to = request.data.get("date_to", "")

        if not date_from or not date_to:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Both date_from and date_to are required (YYYY-MM-DD).",
                        "details": {},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Basic format validation
        date_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        if not date_pattern.match(date_from) or not date_pattern.match(date_to):
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "Dates must be in YYYY-MM-DD format.",
                        "details": {},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if date_from > date_to:
            return Response(
                {
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "date_from must not be after date_to.",
                        "details": {},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        task = generate_audit_pdf.delay(
            date_from=date_from,
            date_to=date_to,
            requested_by_user_id=request.user.id,
        )

        return Response(
            {"task_id": task.id, "status": "queued"},
            status=status.HTTP_202_ACCEPTED,
        )


# ---------------------------------------------------------------------------
# 17.5 — GET /api/v1/audit-log/export/{task_id}/status/
# ---------------------------------------------------------------------------

class AuditLogExportStatusView(APIView):
    """
    GET /api/v1/audit-log/export/{task_id}/status/

    Poll the status of a PDF export task.

    Response while pending
    ----------------------
    { "task_id": "...", "status": "pending" }

    Response on completion
    ----------------------
    {
        "task_id": "...",
        "status": "completed",
        "download_url": "/media/audit_exports/<filename>.pdf",
        "entry_count": <int>
    }

    Response on failure
    -------------------
    { "task_id": "...", "status": "failed", "detail": "<error message>" }
    """

    permission_classes = [IsAdminRole]

    def get(self, request, task_id):
        result = AsyncResult(task_id)

        if result.state == "PENDING":
            return Response({"task_id": task_id, "status": "pending"})

        if result.state == "SUCCESS":
            task_result = result.result or {}
            file_path = task_result.get("file_path", "")
            media_url = getattr(settings, "MEDIA_URL", "/media/")
            download_url = f"{media_url.rstrip('/')}/{file_path}" if file_path else None
            return Response(
                {
                    "task_id": task_id,
                    "status": "completed",
                    "download_url": download_url,
                    "entry_count": task_result.get("entry_count", 0),
                }
            )

        if result.state == "FAILURE":
            return Response(
                {
                    "task_id": task_id,
                    "status": "failed",
                    "detail": str(result.result),
                },
                status=status.HTTP_200_OK,
            )

        # STARTED, RETRY, or other intermediate states
        return Response({"task_id": task_id, "status": result.state.lower()})
