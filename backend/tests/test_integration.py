"""
Integration tests for TenderShield.

These tests exercise full end-to-end pipelines using Django's test client
and in-process Celery task execution (CELERY_TASK_ALWAYS_EAGER=True in
test_settings.py).  They do NOT require a running Docker Compose stack —
the test database (SQLite in-memory) and synchronous Celery execution
replicate the pipeline behaviour faithfully.

Test classes
------------
37.1  BidIngestionPipelineIntegrationTest
        Full bid ingestion → rule evaluation → score recomputation → alert.

37.2  MLRetrainingCycleIntegrationTest
        Ingest labeled tenders → trigger retraining → verify new
        MLModelVersion records and updated scores.

37.3  PDFAuditExportIntegrationTest
        Create audit events → trigger export → verify PDF download.

37.4  EmailNotificationIntegrationTest
        Alert email delivery with mock SMTP; retry logic on failure.

37.5  GraphUpdateIntegrationTest
        Graph update after bid ingestion: CO_BID edges + collusion ring.
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from unittest.mock import MagicMock, call, patch

import django
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_counter = 0


def _uid(prefix: str = "X") -> str:
    global _counter
    _counter += 1
    return f"{prefix}-INTEG-{_counter}"


def _make_tender(
    category: str = "IT",
    estimated_value: Decimal = Decimal("100000.00"),
    deadline_days: int = 30,
    publication_offset_days: int = -10,
):
    from tenders.models import Tender

    now = timezone.now()
    return Tender.objects.create(
        tender_id=_uid("T"),
        title=f"Integration Tender {_uid('TITLE')}",
        category=category,
        estimated_value=estimated_value,
        currency="INR",
        submission_deadline=now + timezone.timedelta(days=deadline_days),
        publication_date=now + timezone.timedelta(days=publication_offset_days),
        buyer_id=_uid("BUYER"),
        buyer_name="Integration Buyer",
    )


def _make_bidder(address: str = "123 Test St", directors: str = "Alice Smith"):
    from bids.models import Bidder

    return Bidder.objects.create(
        bidder_id=_uid("BIDDER"),
        bidder_name=f"Integration Corp {_uid('CORP')}",
        registered_address=address,
        director_names=directors,
    )


def _make_bid(tender, bidder, amount: Decimal = Decimal("90000.00"), is_winner: bool = False):
    from bids.models import Bid

    return Bid.objects.create(
        bid_id=_uid("BID"),
        tender=tender,
        bidder=bidder,
        bid_amount=amount,
        submission_timestamp=timezone.now(),
        is_winner=is_winner,
    )


def _make_admin_user():
    from authentication.models import User, UserRole

    return User.objects.create_user(
        username=_uid("admin"),
        email=f"{_uid('admin')}@test.com",
        password="adminpass123",
        role=UserRole.ADMIN,
    )


def _make_auditor_user():
    from authentication.models import User, UserRole

    return User.objects.create_user(
        username=_uid("auditor"),
        email=f"{_uid('auditor')}@test.com",
        password="auditorpass123",
        role=UserRole.AUDITOR,
    )


def _seed_rule_definitions():
    """Ensure all standard RuleDefinition records exist in the test DB."""
    from detection.models import FlagType, RuleDefinition, Severity

    rules = [
        dict(rule_code=FlagType.SINGLE_BIDDER, severity=Severity.HIGH, parameters={"min_bids": 1}),
        dict(rule_code=FlagType.PRICE_ANOMALY, severity=Severity.MEDIUM, parameters={"threshold": "0.40"}),
        dict(rule_code=FlagType.REPEAT_WINNER, severity=Severity.HIGH, parameters={"threshold": 0.60}),
        dict(rule_code=FlagType.SHORT_DEADLINE, severity=Severity.MEDIUM, parameters={"min_days": 3}),
        dict(rule_code=FlagType.LINKED_ENTITIES, severity=Severity.HIGH, parameters={}),
        dict(rule_code=FlagType.COVER_BID_PATTERN, severity=Severity.HIGH, parameters={"window_days": 30, "min_bids": 3}),
    ]
    for r in rules:
        RuleDefinition.objects.get_or_create(
            rule_code=r["rule_code"],
            defaults=dict(
                description=r["rule_code"],
                severity=r["severity"],
                is_active=True,
                parameters=r["parameters"],
            ),
        )


# ===========================================================================
# 37.1 — Full bid ingestion → rule evaluation → score recomputation → alert
# ===========================================================================

class BidIngestionPipelineIntegrationTest(TestCase):
    """
    Integration test: POST /api/v1/bids/ triggers the full pipeline:
      bid ingestion → rule evaluation → score recomputation → alert creation.

    Uses CELERY_TASK_ALWAYS_EAGER=True so tasks run synchronously in-process.
    Validates: Requirements 3.1, 3.7, 5.1, 5.4, 10.1, 10.3, 11.1
    """

    def setUp(self):
        _seed_rule_definitions()
        self.admin = _make_admin_user()
        self.auditor = _make_auditor_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    # ------------------------------------------------------------------
    # 37.1a — Single bidder triggers SINGLE_BIDDER flag and score > 0
    # ------------------------------------------------------------------

    def test_single_bidder_raises_flag_and_computes_score(self):
        """
        Ingesting one bid on a tender triggers SINGLE_BIDDER (HIGH) flag
        and a non-zero FraudRiskScore.
        """
        from alerts.models import AlertSettings
        from detection.models import FlagType, RedFlag, Severity
        from scoring.models import FraudRiskScore

        tender = _make_tender()
        bidder = _make_bidder()

        # Set alert threshold low enough to fire
        AlertSettings.objects.create(user=self.auditor, category="", threshold=1)

        with patch("alerts.tasks.send_alert_email.delay"):
            response = self.client.post(
                "/api/v1/bids/",
                {
                    "bid_id": _uid("BID"),
                    "tender_id": tender.tender_id,
                    "bidder_id": bidder.bidder_id,
                    "bidder_name": bidder.bidder_name,
                    "bid_amount": "90000.00",
                    "submission_timestamp": timezone.now().isoformat(),
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201, response.data)

        # Rule evaluation: SINGLE_BIDDER flag must be raised
        flag = RedFlag.objects.filter(tender=tender, flag_type=FlagType.SINGLE_BIDDER).first()
        self.assertIsNotNone(flag, "SINGLE_BIDDER RedFlag must be raised after single-bid ingestion")
        self.assertEqual(flag.severity, Severity.HIGH)
        self.assertTrue(flag.is_active)

        # Score recomputation: score must be > 0 (HIGH flag = 25 pts)
        score = FraudRiskScore.objects.filter(tender=tender).order_by("-computed_at").first()
        self.assertIsNotNone(score, "FraudRiskScore must be created after bid ingestion")
        self.assertGreater(score.score, 0)
        self.assertGreaterEqual(score.score, 25)  # at least one HIGH flag

    # ------------------------------------------------------------------
    # 37.1b — Score threshold crossing creates Alert records
    # ------------------------------------------------------------------

    def test_score_above_threshold_creates_alerts_for_all_users(self):
        """
        When the computed score exceeds the configured threshold, Alert records
        are created for all AUDITOR and ADMIN users (Requirement 10.1, 10.3).
        """
        from alerts.models import Alert, AlertSettings

        tender = _make_tender()
        bidder = _make_bidder()

        # Threshold = 1 so any score fires an alert
        AlertSettings.objects.create(user=self.auditor, category="", threshold=1)

        with patch("alerts.tasks.send_alert_email.delay"):
            self.client.post(
                "/api/v1/bids/",
                {
                    "bid_id": _uid("BID"),
                    "tender_id": tender.tender_id,
                    "bidder_id": bidder.bidder_id,
                    "bidder_name": bidder.bidder_name,
                    "bid_amount": "90000.00",
                    "submission_timestamp": timezone.now().isoformat(),
                },
                format="json",
            )

        alerts = Alert.objects.filter(tender=tender)
        self.assertGreater(alerts.count(), 0, "Alerts must be created when score exceeds threshold")

        # Every alert must contain required fields (Requirement 10.3)
        for alert in alerts:
            self.assertEqual(alert.tender_id, tender.pk)
            self.assertIsNotNone(alert.fraud_risk_score)
            self.assertIsNotNone(alert.detail_link)

    # ------------------------------------------------------------------
    # 37.1c — Audit log entries written for bid ingestion and score
    # ------------------------------------------------------------------

    def test_audit_log_entries_written_for_pipeline_events(self):
        """
        Bid ingestion and score computation must each produce an AuditLog entry
        (Requirements 11.1, 11.2).
        """
        from audit.models import AuditLog, EventType

        tender = _make_tender()
        bidder = _make_bidder()

        with patch("alerts.tasks.send_alert_email.delay"):
            self.client.post(
                "/api/v1/bids/",
                {
                    "bid_id": _uid("BID"),
                    "tender_id": tender.tender_id,
                    "bidder_id": bidder.bidder_id,
                    "bidder_name": bidder.bidder_name,
                    "bid_amount": "90000.00",
                    "submission_timestamp": timezone.now().isoformat(),
                },
                format="json",
            )

        bid_logs = AuditLog.objects.filter(event_type=EventType.BID_INGESTED)
        self.assertGreater(bid_logs.count(), 0, "BID_INGESTED AuditLog entry must be written")

        score_logs = AuditLog.objects.filter(event_type=EventType.SCORE_COMPUTED)
        self.assertGreater(score_logs.count(), 0, "SCORE_COMPUTED AuditLog entry must be written")

    # ------------------------------------------------------------------
    # 37.1d — Price anomaly flag fires when bid deviates > 40%
    # ------------------------------------------------------------------

    def test_price_anomaly_flag_fires_for_large_deviation(self):
        """
        A bid that is 50% below estimated_value triggers PRICE_ANOMALY (MEDIUM).
        """
        from detection.models import FlagType, RedFlag, Severity

        # estimated_value = 100,000; winning bid = 40,000 (60% below → > 40% threshold)
        tender = _make_tender(estimated_value=Decimal("100000.00"))
        bidder = _make_bidder()

        with patch("alerts.tasks.send_alert_email.delay"):
            self.client.post(
                "/api/v1/bids/",
                {
                    "bid_id": _uid("BID"),
                    "tender_id": tender.tender_id,
                    "bidder_id": bidder.bidder_id,
                    "bidder_name": bidder.bidder_name,
                    "bid_amount": "40000.00",
                    "submission_timestamp": timezone.now().isoformat(),
                },
                format="json",
            )

        flag = RedFlag.objects.filter(tender=tender, flag_type=FlagType.PRICE_ANOMALY).first()
        self.assertIsNotNone(flag, "PRICE_ANOMALY flag must be raised for 60% deviation")
        self.assertEqual(flag.severity, Severity.MEDIUM)

    # ------------------------------------------------------------------
    # 37.1e — Multiple bids: no SINGLE_BIDDER flag
    # ------------------------------------------------------------------

    def test_multiple_bids_do_not_raise_single_bidder_flag(self):
        """
        When two or more bidders submit bids, SINGLE_BIDDER must NOT be raised.
        """
        from detection.models import FlagType, RedFlag

        tender = _make_tender()
        bidder1 = _make_bidder(address="Addr A", directors="Dir A")
        bidder2 = _make_bidder(address="Addr B", directors="Dir B")

        with patch("alerts.tasks.send_alert_email.delay"):
            for bidder in [bidder1, bidder2]:
                self.client.post(
                    "/api/v1/bids/",
                    {
                        "bid_id": _uid("BID"),
                        "tender_id": tender.tender_id,
                        "bidder_id": bidder.bidder_id,
                        "bidder_name": bidder.bidder_name,
                        "bid_amount": "90000.00",
                        "submission_timestamp": timezone.now().isoformat(),
                    },
                    format="json",
                )

        flag = RedFlag.objects.filter(tender=tender, flag_type=FlagType.SINGLE_BIDDER, is_active=True).first()
        self.assertIsNone(flag, "SINGLE_BIDDER flag must NOT be active when 2 bidders exist")


# ===========================================================================
# 37.2 — ML model retraining cycle
# ===========================================================================

class MLRetrainingCycleIntegrationTest(TestCase):
    """
    Integration test: ingest labeled tenders → trigger retrain_models() →
    verify new MLModelVersion records are created, old ones deactivated,
    and FraudRiskScore rows are updated with ML scores.

    Validates: Requirements 4.2, 4.3, 4.4, 4.6
    """

    def setUp(self):
        _seed_rule_definitions()
        self.admin = _make_admin_user()

    def _ingest_labeled_tenders(self, n: int = 15):
        """
        Create n tenders each with 3+ bids so feature vectors can be computed.
        Returns list of (tender, bids) tuples.
        """
        result = []
        for i in range(n):
            tender = _make_tender(category="Construction")
            bidders = [_make_bidder(address=f"Addr-{_uid('A')}", directors=f"Dir-{_uid('D')}") for _ in range(3)]
            bids = []
            for j, bidder in enumerate(bidders):
                amount = Decimal(str(80000 + j * 5000))
                bid = _make_bid(tender, bidder, amount=amount, is_winner=(j == 0))
                bids.append(bid)
            result.append((tender, bids))
        return result

    # ------------------------------------------------------------------
    # 37.2a — retrain_models creates new MLModelVersion records
    # ------------------------------------------------------------------

    def test_retrain_creates_new_model_version_records(self):
        """
        After retraining, new active MLModelVersion records must exist for
        both ISOLATION_FOREST and RANDOM_FOREST (Requirement 4.4, 4.6).
        """
        from xai.models import MLModelType, MLModelVersion

        self._ingest_labeled_tenders(n=15)

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"ML_MODEL_PATH": tmpdir}):
                # Patch the ML_MODEL_DIR in train module to use tmpdir
                import ml_worker.train as train_mod
                from pathlib import Path
                original_dir = train_mod.ML_MODEL_DIR
                train_mod.ML_MODEL_DIR = Path(tmpdir)
                try:
                    from ml_worker.tasks import retrain_models
                    result = retrain_models()
                finally:
                    train_mod.ML_MODEL_DIR = original_dir

        self.assertEqual(result["status"], "ok", f"retrain_models returned: {result}")

        # New active versions must exist
        if_version = MLModelVersion.objects.filter(
            model_type=MLModelType.ISOLATION_FOREST, is_active=True
        ).first()
        rf_version = MLModelVersion.objects.filter(
            model_type=MLModelType.RANDOM_FOREST, is_active=True
        ).first()

        self.assertIsNotNone(if_version, "Active ISOLATION_FOREST MLModelVersion must exist after retraining")
        self.assertIsNotNone(rf_version, "Active RANDOM_FOREST MLModelVersion must exist after retraining")
        self.assertIsNotNone(if_version.version)
        self.assertIsNotNone(rf_version.version)
        self.assertIsNotNone(if_version.feature_importances)
        self.assertIsNotNone(rf_version.feature_importances)

    # ------------------------------------------------------------------
    # 37.2b — Previous model versions are deactivated
    # ------------------------------------------------------------------

    def test_retrain_deactivates_previous_model_versions(self):
        """
        After a second retraining run, the first model versions must be
        deactivated and only the latest versions are active.
        """
        from xai.models import MLModelType, MLModelVersion

        self._ingest_labeled_tenders(n=15)

        with tempfile.TemporaryDirectory() as tmpdir:
            import ml_worker.train as train_mod
            from pathlib import Path
            original_dir = train_mod.ML_MODEL_DIR
            train_mod.ML_MODEL_DIR = Path(tmpdir)
            try:
                from ml_worker.tasks import retrain_models
                retrain_models()
                first_if = MLModelVersion.objects.filter(
                    model_type=MLModelType.ISOLATION_FOREST, is_active=True
                ).first()
                first_if_version = first_if.version if first_if else None

                # Second retraining run
                retrain_models()
            finally:
                train_mod.ML_MODEL_DIR = original_dir

        # Only one active version per model type
        active_if_count = MLModelVersion.objects.filter(
            model_type=MLModelType.ISOLATION_FOREST, is_active=True
        ).count()
        active_rf_count = MLModelVersion.objects.filter(
            model_type=MLModelType.RANDOM_FOREST, is_active=True
        ).count()

        self.assertEqual(active_if_count, 1, "Exactly one active ISOLATION_FOREST version must exist")
        self.assertEqual(active_rf_count, 1, "Exactly one active RANDOM_FOREST version must exist")

        # The first version must now be inactive
        if first_if_version:
            old_version = MLModelVersion.objects.filter(
                model_type=MLModelType.ISOLATION_FOREST,
                version=first_if_version,
            ).first()
            if old_version:
                self.assertFalse(old_version.is_active, "Previous model version must be deactivated")

    # ------------------------------------------------------------------
    # 37.2c — Retraining writes an AuditLog entry
    # ------------------------------------------------------------------

    def test_retrain_writes_audit_log_entry(self):
        """
        retrain_models() must write a MODEL_RETRAINED AuditLog entry with
        model version, training date, and feature importances (Requirement 4.6).
        """
        from audit.models import AuditLog, EventType

        self._ingest_labeled_tenders(n=15)

        with tempfile.TemporaryDirectory() as tmpdir:
            import ml_worker.train as train_mod
            from pathlib import Path
            original_dir = train_mod.ML_MODEL_DIR
            train_mod.ML_MODEL_DIR = Path(tmpdir)
            try:
                from ml_worker.tasks import retrain_models
                retrain_models()
            finally:
                train_mod.ML_MODEL_DIR = original_dir

        log = AuditLog.objects.filter(event_type=EventType.MODEL_RETRAINED).first()
        self.assertIsNotNone(log, "MODEL_RETRAINED AuditLog entry must be written after retraining")
        self.assertIn("isolation_forest", log.data_snapshot)
        self.assertIn("random_forest", log.data_snapshot)
        self.assertIn("version", log.data_snapshot["isolation_forest"])
        self.assertIn("feature_importances", log.data_snapshot["isolation_forest"])

    # ------------------------------------------------------------------
    # 37.2d — Insufficient data skips retraining gracefully
    # ------------------------------------------------------------------

    def test_retrain_skips_when_insufficient_data(self):
        """
        When fewer than 10 labeled samples are available, retrain_models()
        must return status='skipped' without raising an exception.
        """
        # Only 2 tenders — below the 10-sample minimum
        self._ingest_labeled_tenders(n=2)

        with tempfile.TemporaryDirectory() as tmpdir:
            import ml_worker.train as train_mod
            from pathlib import Path
            original_dir = train_mod.ML_MODEL_DIR
            train_mod.ML_MODEL_DIR = Path(tmpdir)
            try:
                from ml_worker.tasks import retrain_models
                result = retrain_models()
            finally:
                train_mod.ML_MODEL_DIR = original_dir

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "insufficient_data")

    # ------------------------------------------------------------------
    # 37.2e — score_tender uses newly trained models
    # ------------------------------------------------------------------

    def test_score_tender_uses_newly_trained_models(self):
        """
        After retraining, score_tender() must produce non-null ML scores
        for a tender with 3+ bids (Requirements 4.2, 4.3).
        """
        from scoring.models import FraudRiskScore

        self._ingest_labeled_tenders(n=15)

        # Create a new tender with 3 bids to score
        tender = _make_tender(category="Construction")
        bidders = [_make_bidder() for _ in range(3)]
        for j, bidder in enumerate(bidders):
            _make_bid(tender, bidder, amount=Decimal(str(80000 + j * 5000)), is_winner=(j == 0))

        with tempfile.TemporaryDirectory() as tmpdir:
            import ml_worker.train as train_mod
            from pathlib import Path
            original_dir = train_mod.ML_MODEL_DIR
            train_mod.ML_MODEL_DIR = Path(tmpdir)
            try:
                from ml_worker.tasks import retrain_models, score_tender
                retrain_models()
                result = score_tender(tender.pk)
            finally:
                train_mod.ML_MODEL_DIR = original_dir

        self.assertNotIn("error", result, f"score_tender returned error: {result}")
        self.assertIsNotNone(result.get("ml_anomaly_score"), "ml_anomaly_score must be non-null after retraining")
        self.assertIsNotNone(result.get("ml_collusion_score"), "ml_collusion_score must be non-null after retraining")

        # Scores must be in [0, 1]
        self.assertGreaterEqual(result["ml_anomaly_score"], 0.0)
        self.assertLessEqual(result["ml_anomaly_score"], 1.0)
        self.assertGreaterEqual(result["ml_collusion_score"], 0.0)
        self.assertLessEqual(result["ml_collusion_score"], 1.0)


# ===========================================================================
# 37.3 — PDF audit export generation
# ===========================================================================

class PDFAuditExportIntegrationTest(TestCase):
    """
    Integration test: create audit events → POST /api/v1/audit-log/export/ →
    poll status endpoint → verify PDF file is generated and downloadable.

    Validates: Requirements 11.3, 11.4, 11.5
    """

    def setUp(self):
        self.admin = _make_admin_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def _write_audit_events(self, n: int = 5):
        """Write n AuditLog entries for the current date."""
        from audit.models import EventType
        from audit.utils import write_audit_log

        for i in range(n):
            write_audit_log(
                event_type=EventType.TENDER_INGESTED,
                user=self.admin,
                entity_type="Tender",
                entity_id=str(i + 1),
                data_snapshot={"index": i},
                ip_address="127.0.0.1",
            )

    # ------------------------------------------------------------------
    # 37.3a — Export endpoint returns task_id and status=queued
    # ------------------------------------------------------------------

    def test_export_endpoint_returns_task_id(self):
        """
        POST /api/v1/audit-log/export/ must return HTTP 202 with a task_id
        and status='queued' (Requirement 11.4).
        """
        self._write_audit_events()
        today = timezone.now().strftime("%Y-%m-%d")

        response = self.client.post(
            "/api/v1/audit-log/export/",
            {"date_from": today, "date_to": today},
            format="json",
        )

        self.assertEqual(response.status_code, 202, response.data)
        self.assertIn("task_id", response.data)
        self.assertEqual(response.data["status"], "queued")

    # ------------------------------------------------------------------
    # 37.3b — PDF file is generated and contains audit entries
    # ------------------------------------------------------------------

    def test_export_generates_pdf_file(self):
        """
        After the export task completes, a PDF file must exist on disk and
        the status endpoint must return status='completed' with a download_url.
        """
        self._write_audit_events(n=10)
        today = timezone.now().strftime("%Y-%m-%d")

        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                # Trigger export synchronously (CELERY_TASK_ALWAYS_EAGER=True)
                response = self.client.post(
                    "/api/v1/audit-log/export/",
                    {"date_from": today, "date_to": today},
                    format="json",
                )
                self.assertEqual(response.status_code, 202)
                task_id = response.data["task_id"]

                # Poll status
                status_response = self.client.get(
                    f"/api/v1/audit-log/export/{task_id}/status/"
                )

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.data["status"], "completed")
        self.assertIn("download_url", status_response.data)
        self.assertIsNotNone(status_response.data["download_url"])
        self.assertGreater(status_response.data["entry_count"], 0)

    # ------------------------------------------------------------------
    # 37.3c — Export includes all entries in the date range
    # ------------------------------------------------------------------

    def test_export_entry_count_matches_audit_log(self):
        """
        The entry_count in the export result must match the number of
        AuditLog entries in the requested date range.
        """
        from audit.models import AuditLog

        self._write_audit_events(n=7)
        today = timezone.now().strftime("%Y-%m-%d")
        expected_count = AuditLog.objects.filter(
            timestamp__date=timezone.now().date()
        ).count()

        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                response = self.client.post(
                    "/api/v1/audit-log/export/",
                    {"date_from": today, "date_to": today},
                    format="json",
                )
                task_id = response.data["task_id"]
                status_response = self.client.get(
                    f"/api/v1/audit-log/export/{task_id}/status/"
                )

        self.assertEqual(status_response.data["entry_count"], expected_count)

    # ------------------------------------------------------------------
    # 37.3d — Export itself writes an EXPORT_GENERATED AuditLog entry
    # ------------------------------------------------------------------

    def test_export_writes_export_generated_audit_entry(self):
        """
        The export task must write an EXPORT_GENERATED AuditLog entry
        (Requirement 11.1).
        """
        from audit.models import AuditLog, EventType

        self._write_audit_events(n=3)
        today = timezone.now().strftime("%Y-%m-%d")

        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                response = self.client.post(
                    "/api/v1/audit-log/export/",
                    {"date_from": today, "date_to": today},
                    format="json",
                )
                task_id = response.data["task_id"]
                self.client.get(f"/api/v1/audit-log/export/{task_id}/status/")

        export_log = AuditLog.objects.filter(event_type=EventType.EXPORT_GENERATED).first()
        self.assertIsNotNone(export_log, "EXPORT_GENERATED AuditLog entry must be written")
        self.assertEqual(export_log.data_snapshot["date_from"], today)
        self.assertEqual(export_log.data_snapshot["date_to"], today)

    # ------------------------------------------------------------------
    # 37.3e — Export endpoint requires ADMIN role
    # ------------------------------------------------------------------

    def test_export_endpoint_requires_admin_role(self):
        """
        An AUDITOR must receive HTTP 403 when attempting to trigger an export.
        """
        auditor = _make_auditor_user()
        auditor_client = APIClient()
        auditor_client.force_authenticate(user=auditor)
        today = timezone.now().strftime("%Y-%m-%d")

        response = auditor_client.post(
            "/api/v1/audit-log/export/",
            {"date_from": today, "date_to": today},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    # ------------------------------------------------------------------
    # 37.3f — Export with invalid date range returns 400
    # ------------------------------------------------------------------

    def test_export_rejects_invalid_date_range(self):
        """
        date_from after date_to must return HTTP 400.
        """
        response = self.client.post(
            "/api/v1/audit-log/export/",
            {"date_from": "2025-12-31", "date_to": "2025-01-01"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


# ===========================================================================
# 37.4 — Email notification delivery with mock SMTP + retry logic
# ===========================================================================

class EmailNotificationIntegrationTest(TestCase):
    """
    Integration test: alert email delivery via mock SMTP and retry logic.

    Validates: Requirements 10.2, 10.5
    """

    def setUp(self):
        _seed_rule_definitions()
        self.admin = _make_admin_user()
        self.auditor = _make_auditor_user()

    def _create_alert(self, score: int = 85, email_enabled: bool = True):
        """Create an Alert record with an associated AlertSettings."""
        from alerts.models import Alert, AlertSettings, AlertType, DeliveryStatus
        from scoring.models import FraudRiskScore

        tender = _make_tender()
        FraudRiskScore.objects.create(
            tender=tender,
            score=score,
            computed_at=timezone.now(),
        )
        AlertSettings.objects.create(
            user=self.auditor,
            category="",
            threshold=1,
            email_enabled=email_enabled,
        )
        alert = Alert.objects.create(
            tender=tender,
            user=self.auditor,
            alert_type=AlertType.HIGH_RISK_SCORE,
            fraud_risk_score=score,
            top_red_flags=[],
            detail_link=f"/tenders/{tender.pk}",
            delivery_status=DeliveryStatus.PENDING,
            retry_count=0,
            title=tender.title,
        )
        return alert, tender

    # ------------------------------------------------------------------
    # 37.4a — Successful email delivery marks alert as DELIVERED
    # ------------------------------------------------------------------

    def test_successful_email_delivery_marks_alert_delivered(self):
        """
        When send_mail succeeds, the Alert delivery_status must be DELIVERED
        and delivered_at must be set (Requirement 10.2).
        """
        from alerts.models import DeliveryStatus
        from alerts.tasks import send_alert_email

        alert, _ = self._create_alert()

        with patch("alerts.tasks.send_mail") as mock_send:
            mock_send.return_value = 1
            send_alert_email(alert.pk)

        alert.refresh_from_db()
        self.assertEqual(alert.delivery_status, DeliveryStatus.DELIVERED)
        self.assertIsNotNone(alert.delivered_at)
        mock_send.assert_called_once()

    # ------------------------------------------------------------------
    # 37.4b — SMTP failure marks alert as FAILED and logs to AuditLog
    # ------------------------------------------------------------------

    def test_smtp_failure_marks_alert_failed_and_logs(self):
        """
        When send_mail raises an exception, the Alert must be marked FAILED
        and an AuditLog entry must be written (Requirement 10.5).
        """
        from alerts.models import DeliveryStatus
        from alerts.tasks import send_alert_email
        from audit.models import AuditLog, EventType

        alert, _ = self._create_alert()

        with patch("alerts.tasks.send_mail", side_effect=Exception("SMTP connection refused")):
            send_alert_email(alert.pk)

        alert.refresh_from_db()
        self.assertEqual(alert.delivery_status, DeliveryStatus.FAILED)

        fail_log = AuditLog.objects.filter(event_type=EventType.ALERT_FAILED).first()
        self.assertIsNotNone(fail_log, "ALERT_FAILED AuditLog entry must be written on SMTP failure")
        self.assertEqual(int(fail_log.data_snapshot["alert_id"]), alert.pk)

    # ------------------------------------------------------------------
    # 37.4c — retry_failed_emails retries up to MAX_RETRY_COUNT times
    # ------------------------------------------------------------------

    def test_retry_failed_emails_retries_up_to_max(self):
        """
        retry_failed_emails() must retry FAILED alerts and increment
        retry_count on each attempt (Requirement 10.5).
        """
        from alerts.models import DeliveryStatus
        from alerts.tasks import retry_failed_emails

        alert, _ = self._create_alert()
        alert.delivery_status = DeliveryStatus.FAILED
        alert.retry_count = 0
        alert.save(update_fields=["delivery_status", "retry_count"])

        # First retry — still fails
        with patch("alerts.tasks.send_mail", side_effect=Exception("SMTP down")):
            retry_failed_emails()

        alert.refresh_from_db()
        self.assertEqual(alert.retry_count, 1)
        self.assertEqual(alert.delivery_status, DeliveryStatus.FAILED)

        # Second retry — still fails
        with patch("alerts.tasks.send_mail", side_effect=Exception("SMTP down")):
            retry_failed_emails()

        alert.refresh_from_db()
        self.assertEqual(alert.retry_count, 2)

        # Third retry — still fails → PERMANENTLY_FAILED
        with patch("alerts.tasks.send_mail", side_effect=Exception("SMTP down")):
            retry_failed_emails()

        alert.refresh_from_db()
        self.assertEqual(alert.retry_count, 3)
        self.assertEqual(
            alert.delivery_status,
            DeliveryStatus.PERMANENTLY_FAILED,
            "After 3 failed retries, status must be PERMANENTLY_FAILED",
        )

    # ------------------------------------------------------------------
    # 37.4d — retry_failed_emails succeeds on retry after transient failure
    # ------------------------------------------------------------------

    def test_retry_succeeds_after_transient_failure(self):
        """
        If the SMTP server recovers, retry_failed_emails() must mark the
        alert as DELIVERED on the successful retry.
        """
        from alerts.models import DeliveryStatus
        from alerts.tasks import retry_failed_emails

        alert, _ = self._create_alert()
        alert.delivery_status = DeliveryStatus.FAILED
        alert.retry_count = 1
        alert.save(update_fields=["delivery_status", "retry_count"])

        with patch("alerts.tasks.send_mail", return_value=1):
            retry_failed_emails()

        alert.refresh_from_db()
        self.assertEqual(alert.delivery_status, DeliveryStatus.DELIVERED)
        self.assertIsNotNone(alert.delivered_at)

    # ------------------------------------------------------------------
    # 37.4e — Alerts with email_enabled=False are skipped
    # ------------------------------------------------------------------

    def test_email_skipped_when_email_disabled(self):
        """
        When email_enabled=False in AlertSettings, send_alert_email must
        not call send_mail.
        """
        from alerts.tasks import send_alert_email

        alert, _ = self._create_alert(email_enabled=False)

        with patch("alerts.tasks.send_mail") as mock_send:
            send_alert_email(alert.pk)

        mock_send.assert_not_called()

    # ------------------------------------------------------------------
    # 37.4f — Permanently failed alerts are not retried again
    # ------------------------------------------------------------------

    def test_permanently_failed_alerts_not_retried(self):
        """
        Alerts with delivery_status=PERMANENTLY_FAILED must not be picked
        up by retry_failed_emails().
        """
        from alerts.models import DeliveryStatus
        from alerts.tasks import retry_failed_emails

        alert, _ = self._create_alert()
        alert.delivery_status = DeliveryStatus.PERMANENTLY_FAILED
        alert.retry_count = 3
        alert.save(update_fields=["delivery_status", "retry_count"])

        with patch("alerts.tasks.send_mail") as mock_send:
            retry_failed_emails()

        mock_send.assert_not_called()
        alert.refresh_from_db()
        self.assertEqual(alert.retry_count, 3, "retry_count must not change for PERMANENTLY_FAILED alerts")


# ===========================================================================
# 37.5 — Graph update after bid ingestion: CO_BID edges + collusion ring
# ===========================================================================

class GraphUpdateIntegrationTest(TestCase):
    """
    Integration test: bid ingestion → graph update → CO_BID edges created →
    collusion ring detected when ≥ 3 bidders share HIGH-severity flags.

    Validates: Requirements 8.1, 8.4, 8.6, 8.7
    """

    def setUp(self):
        _seed_rule_definitions()
        self.admin = _make_admin_user()
        self.auditor = _make_auditor_user()
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    # ------------------------------------------------------------------
    # 37.5a — CO_BID edges created after bid ingestion via API
    # ------------------------------------------------------------------

    def test_co_bid_edges_created_after_bid_ingestion(self):
        """
        After ingesting bids from multiple bidders on the same tender via
        POST /api/v1/bids/, CO_BID edges must exist between all bidder pairs
        (Requirement 8.1, 8.6).
        """
        from graph.models import EdgeType, GraphEdge, GraphNode

        tender = _make_tender()
        bidders = [_make_bidder(address=f"Addr-{_uid('A')}", directors=f"Dir-{_uid('D')}") for _ in range(3)]

        with patch("alerts.tasks.send_alert_email.delay"):
            for bidder in bidders:
                self.client.post(
                    "/api/v1/bids/",
                    {
                        "bid_id": _uid("BID"),
                        "tender_id": tender.tender_id,
                        "bidder_id": bidder.bidder_id,
                        "bidder_name": bidder.bidder_name,
                        "bid_amount": "90000.00",
                        "submission_timestamp": timezone.now().isoformat(),
                    },
                    format="json",
                )

        # GraphNodes must exist for all bidders
        for bidder in bidders:
            self.assertTrue(
                GraphNode.objects.filter(bidder=bidder).exists(),
                f"GraphNode must exist for bidder {bidder.bidder_id}",
            )

        # CO_BID edges: C(3,2) = 3 edges
        co_bid_count = GraphEdge.objects.filter(
            edge_type=EdgeType.CO_BID,
            tender_id=tender.pk,
        ).count()
        self.assertEqual(co_bid_count, 3, f"Expected 3 CO_BID edges for 3 bidders, got {co_bid_count}")

    # ------------------------------------------------------------------
    # 37.5b — SHARED_ADDRESS edges created for bidders with same address
    # ------------------------------------------------------------------

    def test_shared_address_edges_created_for_linked_bidders(self):
        """
        Bidders sharing a registered address must have SHARED_ADDRESS edges
        after graph update (Requirement 8.3).
        """
        from graph.models import EdgeType, GraphEdge, GraphNode

        shared_address = "42 Shared Lane, Mumbai"
        tender = _make_tender()
        bidder1 = _make_bidder(address=shared_address, directors="Dir A")
        bidder2 = _make_bidder(address=shared_address, directors="Dir B")

        with patch("alerts.tasks.send_alert_email.delay"):
            for bidder in [bidder1, bidder2]:
                self.client.post(
                    "/api/v1/bids/",
                    {
                        "bid_id": _uid("BID"),
                        "tender_id": tender.tender_id,
                        "bidder_id": bidder.bidder_id,
                        "bidder_name": bidder.bidder_name,
                        "bid_amount": "90000.00",
                        "submission_timestamp": timezone.now().isoformat(),
                    },
                    format="json",
                )

        node1 = GraphNode.objects.filter(bidder=bidder1).first()
        node2 = GraphNode.objects.filter(bidder=bidder2).first()
        self.assertIsNotNone(node1)
        self.assertIsNotNone(node2)

        shared_addr_edge = GraphEdge.objects.filter(
            edge_type=EdgeType.SHARED_ADDRESS,
        ).filter(
            source_node__in=[node1, node2],
            target_node__in=[node1, node2],
        ).first()
        self.assertIsNotNone(
            shared_addr_edge,
            "SHARED_ADDRESS edge must exist between bidders sharing an address",
        )

    # ------------------------------------------------------------------
    # 37.5c — Collusion ring detected for 3+ bidders with HIGH flags
    # ------------------------------------------------------------------

    def test_collusion_ring_detected_for_three_bidders_with_high_flags(self):
        """
        When 3+ bidders co-bid on a tender that has a HIGH-severity RedFlag,
        a CollusionRing must be created and an Alert triggered (Requirements
        8.4, 8.7).
        """
        from alerts.models import Alert, AlertType
        from detection.models import FlagType, RedFlag, Severity
        from graph.models import CollusionRing
        from scoring.models import FraudRiskScore

        tender = _make_tender()
        bidders = [_make_bidder(address=f"Addr-{_uid('A')}", directors=f"Dir-{_uid('D')}") for _ in range(3)]

        # Ingest bids
        with patch("alerts.tasks.send_alert_email.delay"):
            for bidder in bidders:
                self.client.post(
                    "/api/v1/bids/",
                    {
                        "bid_id": _uid("BID"),
                        "tender_id": tender.tender_id,
                        "bidder_id": bidder.bidder_id,
                        "bidder_name": bidder.bidder_name,
                        "bid_amount": "90000.00",
                        "submission_timestamp": timezone.now().isoformat(),
                    },
                    format="json",
                )

        # Manually raise a HIGH-severity flag so detect_collusion_rings() fires
        RedFlag.objects.create(
            tender=tender,
            bidder=bidders[0],
            flag_type=FlagType.SINGLE_BIDDER,
            severity=Severity.HIGH,
            rule_version="1.0",
            trigger_data={"bid_count": 1},
            is_active=True,
        )

        # Ensure a FraudRiskScore exists for the alert system
        FraudRiskScore.objects.get_or_create(
            tender=tender,
            defaults={"score": 85, "computed_at": timezone.now()},
        )

        # Trigger graph update + ring detection directly
        from graph.collusion_graph import CollusionGraph
        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        rings = graph.detect_collusion_rings()

        self.assertGreater(len(rings), 0, "CollusionRing must be detected for 3 co-bidders with HIGH flag")

        ring = rings[0]
        self.assertIsNotNone(ring.ring_id, "CollusionRing must have a non-null ring_id")
        self.assertGreaterEqual(ring.member_count, 3)

        # Alert must be triggered for the auditor
        collusion_alert = Alert.objects.filter(
            user=self.auditor,
            alert_type=AlertType.COLLUSION_RING,
        ).first()
        self.assertIsNotNone(
            collusion_alert,
            "COLLUSION_RING Alert must be created for auditor after ring detection",
        )

    # ------------------------------------------------------------------
    # 37.5d — No collusion ring for fewer than 3 bidders
    # ------------------------------------------------------------------

    def test_no_collusion_ring_for_two_bidders(self):
        """
        Two co-bidders must NOT produce a CollusionRing (threshold is 3).
        """
        from detection.models import FlagType, RedFlag, Severity
        from graph.models import CollusionRing

        tender = _make_tender()
        bidders = [_make_bidder() for _ in range(2)]

        with patch("alerts.tasks.send_alert_email.delay"):
            for bidder in bidders:
                self.client.post(
                    "/api/v1/bids/",
                    {
                        "bid_id": _uid("BID"),
                        "tender_id": tender.tender_id,
                        "bidder_id": bidder.bidder_id,
                        "bidder_name": bidder.bidder_name,
                        "bid_amount": "90000.00",
                        "submission_timestamp": timezone.now().isoformat(),
                    },
                    format="json",
                )

        RedFlag.objects.create(
            tender=tender,
            bidder=bidders[0],
            flag_type=FlagType.SINGLE_BIDDER,
            severity=Severity.HIGH,
            rule_version="1.0",
            trigger_data={},
            is_active=True,
        )

        from graph.collusion_graph import CollusionGraph
        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        rings = graph.detect_collusion_rings()

        bidder_pks = {b.pk for b in bidders}
        for ring in rings:
            ring_members = set(ring.member_bidder_ids)
            self.assertFalse(
                ring_members == bidder_pks and len(ring_members) < 3,
                f"CollusionRing must not be created for only 2 bidders: {ring_members}",
            )

    # ------------------------------------------------------------------
    # 37.5e — Graph update is idempotent (no duplicate edges on re-ingest)
    # ------------------------------------------------------------------

    def test_graph_update_is_idempotent(self):
        """
        Calling update_graph() twice for the same tender must not create
        duplicate CO_BID edges (Requirement 8.6).
        """
        from graph.collusion_graph import CollusionGraph
        from graph.models import EdgeType, GraphEdge

        tender = _make_tender()
        bidders = [_make_bidder() for _ in range(3)]
        for bidder in bidders:
            _make_bid(tender, bidder)

        graph = CollusionGraph()
        graph.update_graph(tender.pk)
        graph.update_graph(tender.pk)  # second call

        expected = 3  # C(3,2)
        actual = GraphEdge.objects.filter(edge_type=EdgeType.CO_BID, tender_id=tender.pk).count()
        self.assertEqual(actual, expected, f"Expected {expected} CO_BID edges after idempotent update, got {actual}")
