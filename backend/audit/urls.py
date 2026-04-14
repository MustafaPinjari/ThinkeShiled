from django.urls import path

from audit.views import (
    AuditLogExportStatusView,
    AuditLogExportView,
    AuditLogListView,
)

urlpatterns = [
    # GET  /api/v1/audit-log/
    path("", AuditLogListView.as_view(), name="audit-log-list"),
    # POST /api/v1/audit-log/export/
    path("export/", AuditLogExportView.as_view(), name="audit-log-export"),
    # GET  /api/v1/audit-log/export/{task_id}/status/
    path(
        "export/<str:task_id>/status/",
        AuditLogExportStatusView.as_view(),
        name="audit-log-export-status",
    ),
]
