"""
Alert API views.

Endpoints:
  GET  /api/v1/alerts/                  — list alerts (last 90 days, paginated)
  GET  /api/v1/alerts/{id}/             — alert detail
  GET  /api/v1/alerts/unread/           — unread alerts for current user
  POST /api/v1/alerts/{id}/read/        — mark alert as read
  GET  /api/v1/alerts/settings/         — get current alert settings (ADMIN)
  POST /api/v1/alerts/settings/         — create/update alert settings (ADMIN)
"""

from datetime import timedelta

from django.utils import timezone
from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from alerts.models import Alert, AlertSettings
from alerts.serializers import AlertSerializer, AlertSettingsSerializer
from authentication.permissions import IsAdminRole, IsAuditorOrAdmin


class AlertPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class AlertListView(ListAPIView):
    """
    GET /api/v1/alerts/
    List alerts for the authenticated user from the last 90 days, paginated.
    """
    serializer_class = AlertSerializer
    permission_classes = [IsAuditorOrAdmin]
    pagination_class = AlertPagination

    def get_queryset(self):
        cutoff = timezone.now() - timedelta(days=90)
        return (
            Alert.objects.filter(user=self.request.user, created_at__gte=cutoff)
            .select_related("tender")
            .order_by("-created_at")
        )


class AlertDetailView(RetrieveAPIView):
    """
    GET /api/v1/alerts/{id}/
    Alert detail for the authenticated user.
    """
    serializer_class = AlertSerializer
    permission_classes = [IsAuditorOrAdmin]

    def get_queryset(self):
        return Alert.objects.filter(user=self.request.user).select_related("tender")


class AlertUnreadView(ListAPIView):
    """
    GET /api/v1/alerts/unread/
    Return unread alerts for the authenticated user and mark them as read.
    """
    serializer_class = AlertSerializer
    permission_classes = [IsAuditorOrAdmin]
    pagination_class = None  # return all unread at once

    def get_queryset(self):
        return (
            Alert.objects.filter(user=self.request.user, is_read=False)
            .select_related("tender")
            .order_by("-created_at")
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        data = serializer.data
        # Mark all returned alerts as read
        queryset.update(is_read=True)
        return Response(data)


class AlertMarkReadView(APIView):
    """
    POST /api/v1/alerts/{id}/read/
    Mark a specific alert as read.
    """
    permission_classes = [IsAuditorOrAdmin]

    def post(self, request, pk, *args, **kwargs):
        try:
            alert = Alert.objects.get(pk=pk, user=request.user)
        except Alert.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        alert.is_read = True
        alert.save(update_fields=["is_read"])
        return Response({"detail": "Alert marked as read."}, status=status.HTTP_200_OK)


class AlertSettingsView(APIView):
    """
    GET  /api/v1/alerts/settings/ — get current alert settings (ADMIN)
    POST /api/v1/alerts/settings/ — create/update alert settings (ADMIN)

    AlertSettings are per-user + per-category (unique_together).
    POST upserts: if a setting for (user, category) already exists, it is updated.
    """
    permission_classes = [IsAdminRole]

    def get(self, request, *args, **kwargs):
        settings_qs = AlertSettings.objects.filter(user=request.user).order_by("category")
        serializer = AlertSettingsSerializer(settings_qs, many=True)
        return Response(serializer.data)

    def post(self, request, *args, **kwargs):
        serializer = AlertSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        category = serializer.validated_data.get("category", "")
        threshold = serializer.validated_data["threshold"]
        email_enabled = serializer.validated_data.get("email_enabled", True)

        obj, created = AlertSettings.objects.update_or_create(
            user=request.user,
            category=category,
            defaults={"threshold": threshold, "email_enabled": email_enabled},
        )

        out_serializer = AlertSettingsSerializer(obj)
        status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(out_serializer.data, status=status_code)
