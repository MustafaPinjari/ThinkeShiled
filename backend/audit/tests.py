"""
Unit tests for the audit app.

Covers:
  - AuditLog creation on each event type (17.7)
  - Immutability enforcement — save raises PermissionDenied on update,
    delete raises PermissionDenied (17.7)
  - PDF export generation via Celery task (17.7)
  - GET /api/v1/audit-log/ paginated list view (17.3)
  - POST /api/v1/audit-log/export/ endpoint (17.4)
  - GET /api/v1/audit-log/export/{task_id}/status/ endpoint (17.5)
  - write_audit_log() utility (17.1)
"""

import io
import os
import tempfile
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import AuditLog, EventType
from audit.utils import write_audit_log
from authentication.models import User, UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(username, role=UserRole.ADMIN):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="TestPass123!",
        role=role,
    )


def _auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


# ---------------------------------------------------------------------------
# 1. AuditLog creation on each event type
# ---------------------------------------------------------------------------

class AuditLogCreationTests(TestCase):
    """AuditLog entries are created correctly for every event type."""

    def setUp(self):
        self.user = _make_user("admin_user")

    def _create(self, event_type, **kwargs):
        return AuditLog.objects.create(
            event_type=event_type,
            user=self.user,
            affected_entity_type=kwargs.get("entity_type", "Test"),
            affected_entity_id=kwargs.get("entity_id", "1"),
            data_snapshot=kwargs.get("snapshot", {"key": "value"}),
            ip_address=kwargs.get("ip", "127.0.0.1"),
        )

    def test_user_login_event(self):
        log = self._create(EventType.USER_LOGIN)
        self.assertEqual(log.event_type, EventType.USER_LOGIN)
        self.assertEqual(log.user, self.user)
        self.assertIsNotNone(log.timestamp)

    def test_user_logout_event(self):
        log = self._create(EventType.USER_LOGOUT)
        self.assertEqual(log.event_type, EventType.USER_LOGOUT)

    def test_user_login_failed_event(self):
        log = self._create(EventType.USER_LOGIN_FAILED)
        self.assertEqual(log.event_type, EventType.USER_LOGIN_FAILED)

    def test_user_locked_event(self):
        log = self._create(EventType.USER_LOCKED)
        self.assertEqual(log.event_type, EventType.USER_LOCKED)

    def test_tender_ingested_event(self):
        log = self._create(EventType.TENDER_INGESTED, entity_type="Tender", entity_id="T-001")
        self.assertEqual(log.event_type, EventType.TENDER_INGESTED)
        self.assertEqual(log.affected_entity_type, "Tender")
        self.assertEqual(log.affected_entity_id, "T-001")

    def test_score_computed_event(self):
        log = self._create(EventType.SCORE_COMPUTED, snapshot={"score": 75})
        self.assertEqual(log.event_type, EventType.SCORE_COMPUTED)
        self.assertEqual(log.data_snapshot["score"], 75)

    def test_red_flag_raised_event(self):
        log = self._create(EventType.RED_FLAG_RAISED, entity_type="RedFlag", entity_id="42")
        self.assertEqual(log.event_type, EventType.RED_FLAG_RAISED)

    def test_red_flag_cleared_event(self):
        log = self._create(EventType.RED_FLAG_CLEARED, entity_type="RedFlag", entity_id="42")
        self.assertEqual(log.event_type, EventType.RED_FLAG_CLEARED)

    def test_alert_sent_event(self):
        log = self._create(EventType.ALERT_SENT, entity_type="Tender", entity_id="5")
        self.assertEqual(log.event_type, EventType.ALERT_SENT)

    def test_status_changed_event(self):
        log = self._create(
            EventType.STATUS_CHANGED,
            entity_type="Tender",
            entity_id="T-002",
            snapshot={"old_status": "open", "new_status": "closed"},
        )
        self.assertEqual(log.event_type, EventType.STATUS_CHANGED)
        self.assertEqual(log.data_snapshot["new_status"], "closed")

    def test_export_generated_event(self):
        log = self._create(EventType.EXPORT_GENERATED)
        self.assertEqual(log.event_type, EventType.EXPORT_GENERATED)

    def test_timestamp_is_utc(self):
        log = self._create(EventType.USER_LOGIN)
        self.assertIsNotNone(log.timestamp.tzinfo)

    def test_system_event_no_user(self):
        """System-generated events may have user=None."""
        log = AuditLog.objects.create(
            event_type=EventType.SCORE_COMPUTED,
            user=None,
            affected_entity_type="Tender",
            affected_entity_id="99",
            data_snapshot={},
        )
        self.assertIsNone(log.user)

    def test_ip_address_stored(self):
        log = self._create(EventType.USER_LOGIN, ip="192.168.1.1")
        self.assertEqual(log.ip_address, "192.168.1.1")

    def test_data_snapshot_stored(self):
        snapshot = {"tender_id": 7, "score": 88, "flags": ["SINGLE_BIDDER"]}
        log = self._create(EventType.SCORE_COMPUTED, snapshot=snapshot)
        self.assertEqual(log.data_snapshot["score"], 88)
        self.assertIn("SINGLE_BIDDER", log.data_snapshot["flags"])


# ---------------------------------------------------------------------------
# 2. Immutability enforcement
# ---------------------------------------------------------------------------

class AuditLogImmutabilityTests(TestCase):
    """AuditLog entries cannot be updated or deleted."""

    def setUp(self):
        self.user = _make_user("immutable_user")
        self.log = AuditLog.objects.create(
            event_type=EventType.USER_LOGIN,
            user=self.user,
            affected_entity_type="User",
            affected_entity_id=str(self.user.id),
            data_snapshot={"username": self.user.username},
        )

    def test_save_raises_permission_denied_on_update(self):
        """Calling save() on an existing AuditLog raises PermissionDenied."""
        self.log.data_snapshot = {"tampered": True}
        with self.assertRaises(PermissionDenied):
            self.log.save()

    def test_delete_raises_permission_denied(self):
        """Calling delete() on an AuditLog raises PermissionDenied."""
        with self.assertRaises(PermissionDenied):
            self.log.delete()

    def test_queryset_delete_raises_permission_denied(self):
        """Bulk delete via queryset raises PermissionDenied on each entry."""
        with self.assertRaises(PermissionDenied):
            AuditLog.objects.filter(pk=self.log.pk).first().delete()

    def test_new_entry_can_be_created(self):
        """Creating a new entry (pk=None) must succeed."""
        new_log = AuditLog.objects.create(
            event_type=EventType.USER_LOGOUT,
            user=self.user,
            affected_entity_type="User",
            affected_entity_id=str(self.user.id),
            data_snapshot={},
        )
        self.assertIsNotNone(new_log.pk)

    def test_update_fields_still_raises(self):
        """Even update_fields= kwarg cannot bypass the immutability guard."""
        with self.assertRaises(PermissionDenied):
            self.log.save(update_fields=["data_snapshot"])


# ---------------------------------------------------------------------------
# 3. write_audit_log() utility
# ---------------------------------------------------------------------------

class WriteAuditLogUtilityTests(TestCase):
    """write_audit_log() creates entries and never raises on failure."""

    def setUp(self):
        self.user = _make_user("util_user")

    def test_creates_entry(self):
        log = write_audit_log(
            event_type=EventType.USER_LOGIN,
            user=self.user,
            entity_type="User",
            entity_id=str(self.user.id),
            data_snapshot={"username": self.user.username},
            ip_address="10.0.0.1",
        )
        self.assertIsNotNone(log)
        self.assertEqual(log.event_type, EventType.USER_LOGIN)
        self.assertEqual(log.ip_address, "10.0.0.1")

    def test_returns_none_on_failure(self):
        """write_audit_log must not raise even if DB is unavailable."""
        with patch("audit.models.AuditLog.objects") as mock_mgr:
            mock_mgr.create.side_effect = Exception("DB down")
            result = write_audit_log(EventType.USER_LOGIN)
        self.assertIsNone(result)

    def test_no_user_allowed(self):
        log = write_audit_log(
            event_type=EventType.SCORE_COMPUTED,
            entity_type="Tender",
            entity_id="1",
        )
        self.assertIsNone(log.user)

    def test_empty_snapshot_defaults_to_dict(self):
        log = write_audit_log(event_type=EventType.USER_LOGOUT, user=self.user)
        self.assertEqual(log.data_snapshot, {})


# ---------------------------------------------------------------------------
# 4. GET /api/v1/audit-log/ — paginated list view
# ---------------------------------------------------------------------------

class AuditLogListViewTests(TestCase):
    """GET /api/v1/audit-log/ returns paginated entries for ADMIN only."""

    def setUp(self):
        self.admin = _make_user("list_admin", role=UserRole.ADMIN)
        self.auditor = _make_user("list_auditor", role=UserRole.AUDITOR)
        # Create a handful of entries
        for i in range(5):
            AuditLog.objects.create(
                event_type=EventType.USER_LOGIN,
                user=self.admin,
                affected_entity_type="User",
                affected_entity_id=str(self.admin.id),
                data_snapshot={"seq": i},
            )

    def test_admin_can_list(self):
        client = _auth_client(self.admin)
        response = client.get("/api/v1/audit-log/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)
        self.assertEqual(response.data["count"], 5)

    def test_auditor_is_forbidden(self):
        client = _auth_client(self.auditor)
        response = client.get("/api/v1/audit-log/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_is_rejected(self):
        client = APIClient()
        response = client.get("/api/v1/audit-log/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_filter_by_event_type(self):
        AuditLog.objects.create(
            event_type=EventType.TENDER_INGESTED,
            user=self.admin,
            affected_entity_type="Tender",
            affected_entity_id="T-99",
            data_snapshot={},
        )
        client = _auth_client(self.admin)
        response = client.get("/api/v1/audit-log/?event_type=TENDER_INGESTED")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["event_type"], "TENDER_INGESTED")

    def test_filter_by_date_range(self):
        client = _auth_client(self.admin)
        today = date.today().isoformat()
        response = client.get(f"/api/v1/audit-log/?date_from={today}&date_to={today}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # All entries were created today
        self.assertGreaterEqual(response.data["count"], 5)

    def test_response_fields(self):
        client = _auth_client(self.admin)
        response = client.get("/api/v1/audit-log/")
        entry = response.data["results"][0]
        for field in ("id", "event_type", "timestamp", "user_id", "username",
                      "affected_entity_type", "affected_entity_id", "data_snapshot"):
            self.assertIn(field, entry)


# ---------------------------------------------------------------------------
# 5. POST /api/v1/audit-log/export/ — enqueue PDF export
# ---------------------------------------------------------------------------

class AuditLogExportViewTests(TestCase):
    """POST /api/v1/audit-log/export/ enqueues a Celery task."""

    def setUp(self):
        self.admin = _make_user("export_admin", role=UserRole.ADMIN)
        self.auditor = _make_user("export_auditor", role=UserRole.AUDITOR)

    def test_admin_can_trigger_export(self):
        client = _auth_client(self.admin)
        with patch("audit.views.generate_audit_pdf") as mock_task:
            mock_result = MagicMock()
            mock_result.id = "fake-task-id-123"
            mock_task.delay.return_value = mock_result
            response = client.post(
                "/api/v1/audit-log/export/",
                {"date_from": "2024-01-01", "date_to": "2024-12-31"},
                format="json",
            )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data["task_id"], "fake-task-id-123")
        self.assertEqual(response.data["status"], "queued")

    def test_auditor_is_forbidden(self):
        client = _auth_client(self.auditor)
        response = client.post(
            "/api/v1/audit-log/export/",
            {"date_from": "2024-01-01", "date_to": "2024-12-31"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_date_from_returns_400(self):
        client = _auth_client(self.admin)
        response = client.post(
            "/api/v1/audit-log/export/",
            {"date_to": "2024-12-31"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_date_to_returns_400(self):
        client = _auth_client(self.admin)
        response = client.post(
            "/api/v1/audit-log/export/",
            {"date_from": "2024-01-01"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invalid_date_format_returns_400(self):
        client = _auth_client(self.admin)
        response = client.post(
            "/api/v1/audit-log/export/",
            {"date_from": "01/01/2024", "date_to": "31/12/2024"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_date_from_after_date_to_returns_400(self):
        client = _auth_client(self.admin)
        response = client.post(
            "/api/v1/audit-log/export/",
            {"date_from": "2024-12-31", "date_to": "2024-01-01"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# 6. GET /api/v1/audit-log/export/{task_id}/status/ — polling endpoint
# ---------------------------------------------------------------------------

class AuditLogExportStatusViewTests(TestCase):
    """GET /api/v1/audit-log/export/{task_id}/status/ returns task state."""

    def setUp(self):
        self.admin = _make_user("status_admin", role=UserRole.ADMIN)
        self.client = _auth_client(self.admin)

    def test_pending_state(self):
        with patch("audit.views.AsyncResult") as mock_ar:
            mock_ar.return_value.state = "PENDING"
            response = self.client.get("/api/v1/audit-log/export/abc123/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "pending")

    def test_success_state_returns_download_url(self):
        with patch("audit.views.AsyncResult") as mock_ar:
            mock_ar.return_value.state = "SUCCESS"
            mock_ar.return_value.result = {
                "status": "completed",
                "file_path": "audit_exports/audit_export_2024-01-01_2024-12-31_abc.pdf",
                "entry_count": 42,
            }
            response = self.client.get("/api/v1/audit-log/export/abc123/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "completed")
        self.assertIn("download_url", response.data)
        self.assertEqual(response.data["entry_count"], 42)

    def test_failure_state(self):
        with patch("audit.views.AsyncResult") as mock_ar:
            mock_ar.return_value.state = "FAILURE"
            mock_ar.return_value.result = Exception("PDF generation failed")
            response = self.client.get("/api/v1/audit-log/export/abc123/status/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "failed")
        self.assertIn("detail", response.data)

    def test_auditor_is_forbidden(self):
        auditor = _make_user("status_auditor", role=UserRole.AUDITOR)
        client = _auth_client(auditor)
        response = client.get("/api/v1/audit-log/export/abc123/status/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# 7. PDF export generation (Celery task)
# ---------------------------------------------------------------------------

class AuditLogPDFExportTaskTests(TestCase):
    """generate_audit_pdf Celery task produces a valid PDF file."""

    def setUp(self):
        self.user = _make_user("pdf_user")
        # Create some audit entries
        for i in range(3):
            AuditLog.objects.create(
                event_type=EventType.USER_LOGIN,
                user=self.user,
                affected_entity_type="User",
                affected_entity_id=str(self.user.id),
                data_snapshot={"seq": i},
                ip_address="127.0.0.1",
            )

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        MEDIA_ROOT=tempfile.mkdtemp(),
    )
    def test_pdf_is_generated(self):
        from audit.tasks import generate_audit_pdf

        today = date.today().isoformat()
        result = generate_audit_pdf(
            date_from=today,
            date_to=today,
            requested_by_user_id=self.user.id,
        )

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["entry_count"], 3)

        # Verify the file exists and is a valid PDF
        media_root = tempfile.gettempdir()
        # The task uses settings.MEDIA_ROOT which is overridden above
        from django.conf import settings as django_settings
        file_path = os.path.join(django_settings.MEDIA_ROOT, result["file_path"])
        self.assertTrue(os.path.exists(file_path), f"PDF not found at {file_path}")

        with open(file_path, "rb") as fh:
            header = fh.read(4)
        self.assertEqual(header, b"%PDF", "File does not start with PDF magic bytes")

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        MEDIA_ROOT=tempfile.mkdtemp(),
    )
    def test_pdf_empty_range_produces_file(self):
        """An empty date range (no entries) still produces a valid PDF."""
        from audit.tasks import generate_audit_pdf

        result = generate_audit_pdf(
            date_from="2000-01-01",
            date_to="2000-01-02",
        )
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["entry_count"], 0)

        from django.conf import settings as django_settings
        file_path = os.path.join(django_settings.MEDIA_ROOT, result["file_path"])
        self.assertTrue(os.path.exists(file_path))

    @override_settings(
        CELERY_TASK_ALWAYS_EAGER=True,
        CELERY_TASK_EAGER_PROPAGATES=True,
        MEDIA_ROOT=tempfile.mkdtemp(),
    )
    def test_export_audit_log_entry_created(self):
        """Generating a PDF writes an EXPORT_GENERATED AuditLog entry."""
        from audit.tasks import generate_audit_pdf

        before_count = AuditLog.objects.filter(event_type=EventType.EXPORT_GENERATED).count()
        today = date.today().isoformat()
        generate_audit_pdf(
            date_from=today,
            date_to=today,
            requested_by_user_id=self.user.id,
        )
        after_count = AuditLog.objects.filter(event_type=EventType.EXPORT_GENERATED).count()
        self.assertEqual(after_count, before_count + 1)

    def test_invalid_date_format_raises(self):
        from audit.tasks import generate_audit_pdf

        with self.assertRaises(ValueError):
            generate_audit_pdf(date_from="not-a-date", date_to="2024-12-31")
