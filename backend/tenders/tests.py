import io
import csv as csv_module
from datetime import datetime, timezone as dt_tz

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.models import User, UserRole
from tenders.models import Tender, TenderStatus

TENDERS_URL = "/api/v1/tenders/"
UPLOAD_URL = "/api/v1/tenders/upload/"

DEADLINE = "2030-12-31T23:59:59Z"

VALID_TENDER_PAYLOAD = {
    "tender_id": "T-001",
    "title": "Road Construction",
    "category": "Infrastructure",
    "estimated_value": "1000000.00",
    "currency": "INR",
    "submission_deadline": DEADLINE,
    "buyer_id": "B-001",
    "buyer_name": "Ministry of Roads",
}


def _make_csv(rows: list[dict]) -> bytes:
    """Build a CSV bytes object from a list of dicts."""
    if not rows:
        return b""
    fieldnames = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv_module.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _valid_row(tender_id: str = "T-001") -> dict:
    return {
        "tender_id": tender_id,
        "title": "Test Tender",
        "category": "Works",
        "estimated_value": "500000.00",
        "currency": "INR",
        "submission_deadline": DEADLINE,
        "buyer_id": "B-001",
        "buyer_name": "Test Buyer",
    }


class BaseTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@example.com",
            password="admin-pass-123",
            role=UserRole.ADMIN,
        )
        self.auditor = User.objects.create_user(
            username="auditor",
            email="auditor@example.com",
            password="auditor-pass-123",
            role=UserRole.AUDITOR,
        )

    def _auth(self, user: User):
        token = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(token.access_token)}")

    def _auth_admin(self):
        self._auth(self.admin)

    def _auth_auditor(self):
        self._auth(self.auditor)


# ---------------------------------------------------------------------------
# CSV upload tests
# ---------------------------------------------------------------------------

class CSVUploadTests(BaseTestCase):

    def test_csv_valid_rows(self):
        """All rows with mandatory fields should be accepted."""
        self._auth_admin()
        rows = [_valid_row(f"T-{i:03d}") for i in range(1, 6)]
        csv_bytes = _make_csv(rows)
        resp = self.client.post(
            UPLOAD_URL,
            {"file": io.BytesIO(csv_bytes)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["accepted"], 5)
        self.assertEqual(resp.data["rejected"], 0)
        self.assertEqual(resp.data["rejected_rows"], [])
        self.assertEqual(Tender.objects.count(), 5)

    def test_csv_missing_mandatory_field(self):
        """A row missing estimated_value should be rejected with a reason."""
        self._auth_admin()
        row = _valid_row("T-MISS")
        del row["estimated_value"]
        csv_bytes = _make_csv([row])
        resp = self.client.post(
            UPLOAD_URL,
            {"file": io.BytesIO(csv_bytes)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["accepted"], 0)
        self.assertEqual(resp.data["rejected"], 1)
        rejected = resp.data["rejected_rows"][0]
        self.assertEqual(rejected["tender_id"], "T-MISS")
        self.assertIn("estimated_value", rejected["reason"])

    def test_csv_duplicate_tender_id_in_db(self):
        """A row whose tender_id already exists in DB should be rejected; original unchanged."""
        self._auth_admin()
        # Pre-create a tender
        Tender.objects.create(
            tender_id="T-DUP",
            title="Original",
            category="Works",
            estimated_value="100.00",
            currency="INR",
            submission_deadline=datetime(2030, 12, 31, tzinfo=dt_tz.utc),
            buyer_id="B-001",
            buyer_name="Original Buyer",
        )
        row = _valid_row("T-DUP")
        row["title"] = "Should Not Overwrite"
        csv_bytes = _make_csv([row])
        resp = self.client.post(
            UPLOAD_URL,
            {"file": io.BytesIO(csv_bytes)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["accepted"], 0)
        self.assertEqual(resp.data["rejected"], 1)
        # Original record unchanged
        original = Tender.objects.get(tender_id="T-DUP")
        self.assertEqual(original.title, "Original")

    def test_csv_duplicate_tender_id_within_batch(self):
        """Two rows with the same tender_id in one batch — second should be rejected."""
        self._auth_admin()
        rows = [_valid_row("T-SAME"), _valid_row("T-SAME")]
        csv_bytes = _make_csv(rows)
        resp = self.client.post(
            UPLOAD_URL,
            {"file": io.BytesIO(csv_bytes)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["accepted"], 1)
        self.assertEqual(resp.data["rejected"], 1)
        self.assertIn("T-SAME", resp.data["rejected_rows"][0]["tender_id"])
        self.assertEqual(Tender.objects.filter(tender_id="T-SAME").count(), 1)

    def test_csv_batch_size(self):
        """Upload 100 valid rows — all should be accepted (smoke test for batch logic)."""
        self._auth_admin()
        rows = [_valid_row(f"T-{i:04d}") for i in range(1, 101)]
        csv_bytes = _make_csv(rows)
        resp = self.client.post(
            UPLOAD_URL,
            {"file": io.BytesIO(csv_bytes)},
            format="multipart",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["accepted"], 100)
        self.assertEqual(resp.data["rejected"], 0)
        self.assertEqual(Tender.objects.count(), 100)


# ---------------------------------------------------------------------------
# Single tender creation tests
# ---------------------------------------------------------------------------

class SingleTenderCreateTests(BaseTestCase):

    def test_single_tender_create_admin(self):
        """ADMIN can create a tender — returns 201."""
        self._auth_admin()
        resp = self.client.post(TENDERS_URL, VALID_TENDER_PAYLOAD, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["tender_id"], "T-001")
        self.assertTrue(Tender.objects.filter(tender_id="T-001").exists())

    def test_single_tender_create_auditor(self):
        """AUDITOR cannot create a tender — returns 403."""
        self._auth_auditor()
        resp = self.client.post(TENDERS_URL, VALID_TENDER_PAYLOAD, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_single_tender_duplicate(self):
        """Posting a tender with an existing tender_id returns 400."""
        self._auth_admin()
        self.client.post(TENDERS_URL, VALID_TENDER_PAYLOAD, format="json")
        resp = self.client.post(TENDERS_URL, VALID_TENDER_PAYLOAD, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.data["error"]["code"], "VALIDATION_ERROR")


# ---------------------------------------------------------------------------
# List and detail tests
# ---------------------------------------------------------------------------

class TenderListTests(BaseTestCase):

    def _create_tenders(self, count: int):
        for i in range(1, count + 1):
            Tender.objects.create(
                tender_id=f"T-{i:04d}",
                title=f"Tender {i}",
                category="Works" if i % 2 == 0 else "Services",
                estimated_value="100000.00",
                currency="INR",
                submission_deadline=datetime(2030, 12, 31, tzinfo=dt_tz.utc),
                buyer_id="B-001",
                buyer_name="Test Buyer",
            )

    def test_tender_list_pagination(self):
        """GET /api/v1/tenders/ returns paginated response."""
        self._auth_auditor()
        self._create_tenders(25)
        resp = self.client.get(TENDERS_URL)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("count", resp.data)
        self.assertIn("results", resp.data)
        self.assertEqual(resp.data["count"], 25)
        # Default page_size is 20
        self.assertEqual(len(resp.data["results"]), 20)

    def test_tender_list_filter_category(self):
        """Filter by category returns only matching tenders."""
        self._auth_auditor()
        self._create_tenders(10)
        resp = self.client.get(TENDERS_URL, {"category": "Works"})
        self.assertEqual(resp.status_code, 200)
        for result in resp.data["results"]:
            self.assertIn("Works", result["category"])

    def test_tender_detail(self):
        """GET /api/v1/tenders/{id}/ returns tender fields."""
        self._auth_auditor()
        tender = Tender.objects.create(
            tender_id="T-DETAIL",
            title="Detail Test",
            category="Works",
            estimated_value="999.99",
            currency="USD",
            submission_deadline=datetime(2030, 6, 1, tzinfo=dt_tz.utc),
            buyer_id="B-999",
            buyer_name="Detail Buyer",
        )
        resp = self.client.get(f"{TENDERS_URL}{tender.pk}/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["tender_id"], "T-DETAIL")
        self.assertEqual(resp.data["title"], "Detail Test")
        self.assertEqual(resp.data["buyer_name"], "Detail Buyer")
