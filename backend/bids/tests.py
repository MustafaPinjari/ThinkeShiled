"""
Unit tests for the Bid ingestion API (task 7).

Covers:
- BidSerializer validation (all required fields, invalid values)
- POST /api/v1/bids/ — single bid creation, duplicate rejection, AuditLog entry
- POST /api/v1/bids/bulk/ — bulk ingestion, partial failures
- GET  /api/v1/bids/?tender_id= — list view, auth enforcement
- Post-ingestion Celery task enqueueing
"""

from unittest.mock import patch, call

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from audit.models import AuditLog, EventType
from authentication.models import User, UserRole
from bids.models import Bid, Bidder
from bids.serializers import BidSerializer
from tenders.models import Tender


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_tender(**kwargs):
    defaults = dict(
        tender_id="T-001",
        title="Test Tender",
        category="Construction",
        estimated_value="100000.00",
        currency="INR",
        submission_deadline="2025-12-31T00:00:00Z",
        buyer_id="B-001",
        buyer_name="Govt Dept",
        status="ACTIVE",
    )
    defaults.update(kwargs)
    return Tender.objects.create(**defaults)


def make_user(username="admin", role=UserRole.ADMIN):
    return User.objects.create_user(
        username=username, email=f"{username}@example.com", password="pass", role=role
    )


def bid_payload(**kwargs):
    defaults = dict(
        bid_id="BID-001",
        tender_id="T-001",
        bidder_id="BIDDER-001",
        bidder_name="Acme Corp",
        bid_amount="90000.00",
        submission_timestamp="2025-12-01T10:00:00Z",
    )
    defaults.update(kwargs)
    return defaults


# ---------------------------------------------------------------------------
# BidSerializer tests
# ---------------------------------------------------------------------------

class BidSerializerTest(TestCase):
    def setUp(self):
        self.tender = make_tender()

    def test_valid_payload_is_accepted(self):
        s = BidSerializer(data=bid_payload())
        self.assertTrue(s.is_valid(), s.errors)

    def test_missing_bid_id_is_rejected(self):
        data = bid_payload()
        del data["bid_id"]
        s = BidSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("bid_id", s.errors)

    def test_missing_tender_id_is_rejected(self):
        data = bid_payload()
        del data["tender_id"]
        s = BidSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("tender_id", s.errors)

    def test_missing_bidder_id_is_rejected(self):
        data = bid_payload()
        del data["bidder_id"]
        s = BidSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("bidder_id", s.errors)

    def test_missing_bidder_name_is_rejected(self):
        data = bid_payload()
        del data["bidder_name"]
        s = BidSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("bidder_name", s.errors)

    def test_missing_bid_amount_is_rejected(self):
        data = bid_payload()
        del data["bid_amount"]
        s = BidSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("bid_amount", s.errors)

    def test_missing_submission_timestamp_is_rejected(self):
        data = bid_payload()
        del data["submission_timestamp"]
        s = BidSerializer(data=data)
        self.assertFalse(s.is_valid())
        self.assertIn("submission_timestamp", s.errors)

    def test_nonexistent_tender_id_is_rejected(self):
        s = BidSerializer(data=bid_payload(tender_id="DOES-NOT-EXIST"))
        self.assertFalse(s.is_valid())
        self.assertIn("tender_id", str(s.errors))

    def test_zero_bid_amount_is_rejected(self):
        s = BidSerializer(data=bid_payload(bid_amount="0.00"))
        self.assertFalse(s.is_valid())
        self.assertIn("bid_amount", s.errors)

    def test_negative_bid_amount_is_rejected(self):
        s = BidSerializer(data=bid_payload(bid_amount="-100.00"))
        self.assertFalse(s.is_valid())
        self.assertIn("bid_amount", s.errors)

    def test_xss_in_bidder_name_is_sanitized(self):
        s = BidSerializer(data=bid_payload(bidder_name="<script>alert(1)</script>Acme"))
        self.assertTrue(s.is_valid(), s.errors)
        self.assertNotIn("<script>", s.validated_data["bidder_name"])

    def test_create_bid_upserts_bidder(self):
        s = BidSerializer(data=bid_payload())
        self.assertTrue(s.is_valid())
        bid, bidder, created = s.create_bid()
        self.assertTrue(created)
        self.assertEqual(bid.bid_id, "BID-001")
        self.assertEqual(bidder.bidder_id, "BIDDER-001")

    def test_create_bid_updates_existing_bidder(self):
        Bidder.objects.create(bidder_id="BIDDER-001", bidder_name="Old Name")
        s = BidSerializer(data=bid_payload(bidder_name="New Name"))
        self.assertTrue(s.is_valid())
        _, bidder, created = s.create_bid()
        self.assertFalse(created)
        self.assertEqual(bidder.bidder_name, "New Name")


# ---------------------------------------------------------------------------
# POST /api/v1/bids/ — single bid creation
# ---------------------------------------------------------------------------

PIPELINE_TASKS = [
    "bids.tasks.evaluate_rules_task",
    "bids.tasks.compute_score_task",
    "bids.tasks.score_ml_task",
    "bids.tasks.update_company_profile_task",
    "bids.tasks.update_graph_task",
]


class BidCreateViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user("admin", UserRole.ADMIN)
        self.auditor = make_user("auditor", UserRole.AUDITOR)
        self.tender = make_tender()
        self.url = reverse("bid-list-create")

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    @patch("bids.views.evaluate_rules_task")
    @patch("bids.views.compute_score_task")
    @patch("bids.views.score_ml_task")
    @patch("bids.views.update_company_profile_task")
    @patch("bids.views.update_graph_task")
    def test_admin_can_create_bid(self, mock_graph, mock_profile, mock_ml, mock_score, mock_rules):
        self._auth(self.admin)
        resp = self.client.post(self.url, bid_payload(), format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["bid_id"], "BID-001")
        self.assertTrue(Bid.objects.filter(bid_id="BID-001").exists())

    @patch("bids.views.evaluate_rules_task")
    @patch("bids.views.compute_score_task")
    @patch("bids.views.score_ml_task")
    @patch("bids.views.update_company_profile_task")
    @patch("bids.views.update_graph_task")
    def test_bid_creation_writes_audit_log(self, mock_graph, mock_profile, mock_ml, mock_score, mock_rules):
        self._auth(self.admin)
        self.client.post(self.url, bid_payload(), format="json")
        log = AuditLog.objects.filter(event_type=EventType.BID_INGESTED).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.affected_entity_id, "BID-001")
        self.assertEqual(log.user, self.admin)

    @patch("bids.views.evaluate_rules_task")
    @patch("bids.views.compute_score_task")
    @patch("bids.views.score_ml_task")
    @patch("bids.views.update_company_profile_task")
    @patch("bids.views.update_graph_task")
    def test_post_ingestion_tasks_are_enqueued(self, mock_graph, mock_profile, mock_ml, mock_score, mock_rules):
        self._auth(self.admin)
        self.client.post(self.url, bid_payload(), format="json")
        mock_rules.delay.assert_called_once()
        mock_score.delay.assert_called_once()
        mock_ml.delay.assert_called_once()
        mock_profile.delay.assert_called_once()
        mock_graph.delay.assert_called_once()

    def test_auditor_cannot_create_bid(self):
        self._auth(self.auditor)
        resp = self.client.post(self.url, bid_payload(), format="json")
        self.assertEqual(resp.status_code, 403)

    def test_unauthenticated_cannot_create_bid(self):
        resp = self.client.post(self.url, bid_payload(), format="json")
        self.assertEqual(resp.status_code, 401)

    @patch("bids.views.evaluate_rules_task")
    @patch("bids.views.compute_score_task")
    @patch("bids.views.score_ml_task")
    @patch("bids.views.update_company_profile_task")
    @patch("bids.views.update_graph_task")
    def test_duplicate_bid_id_is_rejected(self, mock_graph, mock_profile, mock_ml, mock_score, mock_rules):
        self._auth(self.admin)
        self.client.post(self.url, bid_payload(), format="json")
        resp = self.client.post(self.url, bid_payload(), format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("bid_id", str(resp.data))

    def test_missing_required_field_returns_400(self):
        self._auth(self.admin)
        data = bid_payload()
        del data["bid_amount"]
        resp = self.client.post(self.url, data, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_nonexistent_tender_returns_400(self):
        self._auth(self.admin)
        resp = self.client.post(self.url, bid_payload(tender_id="GHOST"), format="json")
        self.assertEqual(resp.status_code, 400)


# ---------------------------------------------------------------------------
# POST /api/v1/bids/bulk/ — bulk ingestion
# ---------------------------------------------------------------------------

class BidBulkCreateViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user("admin", UserRole.ADMIN)
        self.auditor = make_user("auditor", UserRole.AUDITOR)
        self.tender = make_tender()
        self.url = reverse("bid-bulk-create")

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    @patch("bids.views.evaluate_rules_task")
    @patch("bids.views.compute_score_task")
    @patch("bids.views.score_ml_task")
    @patch("bids.views.update_company_profile_task")
    @patch("bids.views.update_graph_task")
    def test_bulk_create_all_valid(self, mock_graph, mock_profile, mock_ml, mock_score, mock_rules):
        self._auth(self.admin)
        payload = [
            bid_payload(bid_id="BID-001", bidder_id="BIDDER-001"),
            bid_payload(bid_id="BID-002", bidder_id="BIDDER-002"),
        ]
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["accepted"], 2)
        self.assertEqual(resp.data["rejected"], 0)
        self.assertEqual(Bid.objects.count(), 2)

    @patch("bids.views.evaluate_rules_task")
    @patch("bids.views.compute_score_task")
    @patch("bids.views.score_ml_task")
    @patch("bids.views.update_company_profile_task")
    @patch("bids.views.update_graph_task")
    def test_bulk_create_partial_failure(self, mock_graph, mock_profile, mock_ml, mock_score, mock_rules):
        self._auth(self.admin)
        payload = [
            bid_payload(bid_id="BID-001"),                          # valid
            bid_payload(bid_id="BID-002", tender_id="GHOST"),       # invalid tender
        ]
        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["accepted"], 1)
        self.assertEqual(resp.data["rejected"], 1)
        self.assertEqual(resp.data["rejected_bids"][0]["bid_id"], "BID-002")

    @patch("bids.views.evaluate_rules_task")
    @patch("bids.views.compute_score_task")
    @patch("bids.views.score_ml_task")
    @patch("bids.views.update_company_profile_task")
    @patch("bids.views.update_graph_task")
    def test_bulk_duplicate_bid_id_is_rejected(self, mock_graph, mock_profile, mock_ml, mock_score, mock_rules):
        self._auth(self.admin)
        # First create BID-001
        self.client.post(reverse("bid-list-create"), bid_payload(bid_id="BID-001"), format="json")
        # Now bulk with same bid_id
        resp = self.client.post(self.url, [bid_payload(bid_id="BID-001")], format="json")
        self.assertEqual(resp.data["rejected"], 1)

    def test_non_list_body_returns_400(self):
        self._auth(self.admin)
        resp = self.client.post(self.url, {"bid_id": "X"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_auditor_cannot_bulk_create(self):
        self._auth(self.auditor)
        resp = self.client.post(self.url, [bid_payload()], format="json")
        self.assertEqual(resp.status_code, 403)

    @patch("bids.views.evaluate_rules_task")
    @patch("bids.views.compute_score_task")
    @patch("bids.views.score_ml_task")
    @patch("bids.views.update_company_profile_task")
    @patch("bids.views.update_graph_task")
    def test_bulk_enqueues_tasks_per_bid(self, mock_graph, mock_profile, mock_ml, mock_score, mock_rules):
        self._auth(self.admin)
        payload = [
            bid_payload(bid_id="BID-001", bidder_id="BIDDER-001"),
            bid_payload(bid_id="BID-002", bidder_id="BIDDER-002"),
        ]
        self.client.post(self.url, payload, format="json")
        self.assertEqual(mock_rules.delay.call_count, 2)
        self.assertEqual(mock_profile.delay.call_count, 2)


# ---------------------------------------------------------------------------
# GET /api/v1/bids/?tender_id= — list view
# ---------------------------------------------------------------------------

class BidListViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = make_user("admin", UserRole.ADMIN)
        self.auditor = make_user("auditor", UserRole.AUDITOR)
        self.tender = make_tender()
        self.bidder = Bidder.objects.create(bidder_id="BIDDER-001", bidder_name="Acme")
        Bid.objects.create(
            bid_id="BID-001",
            tender=self.tender,
            bidder=self.bidder,
            bid_amount="90000.00",
            submission_timestamp="2025-12-01T10:00:00Z",
        )
        self.url = reverse("bid-list-create")

    def test_auditor_can_list_bids(self):
        self.client.force_authenticate(user=self.auditor)
        resp = self.client.get(self.url, {"tender_id": "T-001"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["bid_id"], "BID-001")

    def test_admin_can_list_bids(self):
        self.client.force_authenticate(user=self.admin)
        resp = self.client.get(self.url, {"tender_id": "T-001"})
        self.assertEqual(resp.status_code, 200)

    def test_unauthenticated_cannot_list_bids(self):
        resp = self.client.get(self.url, {"tender_id": "T-001"})
        self.assertEqual(resp.status_code, 401)

    def test_missing_tender_id_returns_400(self):
        self.client.force_authenticate(user=self.auditor)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 400)

    def test_nonexistent_tender_returns_404(self):
        self.client.force_authenticate(user=self.auditor)
        resp = self.client.get(self.url, {"tender_id": "GHOST"})
        self.assertEqual(resp.status_code, 404)
