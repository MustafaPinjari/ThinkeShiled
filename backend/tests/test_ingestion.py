# Feature: tender-shield
# Property-Based Tests: Ingestion (Properties 4, 5, 6)

import io
import csv
from decimal import Decimal
from unittest.mock import patch

from django.test import override_settings
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from authentication.models import User, UserRole
from tenders.models import Tender
from bids.models import Bid, Bidder

UPLOAD_URL = "/api/v1/tenders/upload/"
TENDER_URL = "/api/v1/tenders/"
BID_URL = "/api/v1/bids/"

VALID_PASSWORD = "ValidPass-PBT-123!"

_BASE_JWT = {
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": "test-secret-key-for-unit-tests",
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
    "REFRESH_TOKEN_LIFETIME": __import__("datetime").timedelta(days=7),
    "ACCESS_TOKEN_LIFETIME": __import__("datetime").timedelta(seconds=3600),
}

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

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_safe_text = st.text(
    alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="-_ "),
    min_size=1,
    max_size=50,
).filter(lambda s: s.strip())

_counter = {"n": 0}


def _next_id(prefix: str) -> str:
    _counter["n"] += 1
    return f"{prefix}-{_counter['n']}"


@st.composite
def valid_tender_row(draw, tender_id=None):
    """Generate a complete, valid CSV row dict for a tender."""
    return {
        "tender_id": tender_id or _next_id("T-PBT4"),
        "title": draw(_safe_text),
        "category": draw(_safe_text),
        "estimated_value": str(draw(st.decimals(min_value=Decimal("1.00"), max_value=Decimal("1e12"),
                                                allow_nan=False, allow_infinity=False,
                                                places=2))),
        "currency": draw(st.sampled_from(["INR", "USD", "EUR", "GBP"])),
        "submission_deadline": "2030-12-31T23:59:59Z",
        "buyer_id": draw(_safe_text),
        "buyer_name": draw(_safe_text),
    }


@st.composite
def invalid_tender_row(draw):
    """Generate a CSV row with at least one mandatory field missing."""
    row = draw(valid_tender_row())
    # Remove one or more mandatory fields
    fields_to_remove = draw(
        st.lists(st.sampled_from(MANDATORY_CSV_FIELDS), min_size=1, max_size=len(MANDATORY_CSV_FIELDS), unique=True)
    )
    for field in fields_to_remove:
        row[field] = ""  # blank = missing per the view's validation logic
    return row, fields_to_remove


def _make_csv(rows: list[dict]) -> bytes:
    """Serialize a list of row dicts to CSV bytes."""
    if not rows:
        return b",".join(f.encode() for f in MANDATORY_CSV_FIELDS) + b"\n"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _admin_client() -> tuple[APIClient, User]:
    _counter["n"] += 1
    user = User.objects.create_user(
        username=f"pbt_admin_{_counter['n']}",
        email=f"pbt_admin_{_counter['n']}@example.com",
        password=VALID_PASSWORD,
        role=UserRole.ADMIN,
    )
    client = APIClient()
    with override_settings(SIMPLE_JWT=_BASE_JWT):
        refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client, user


# ---------------------------------------------------------------------------
# Property 4 — CSV Schema Validation
# Feature: tender-shield, Property 4: CSV Schema Validation
# ---------------------------------------------------------------------------

class CSVSchemaValidationTest(TestCase):
    """
    Property 4: For any CSV row with all mandatory fields present and valid,
    the row is accepted and stored. For any row missing one or more mandatory
    fields, the row is rejected with a reason in the validation report.
    Validates: Requirements 2.1, 2.2
    """

    @given(valid_tender_row())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_valid_row_is_accepted_and_stored(self, row):
        # Feature: tender-shield, Property 4: CSV Schema Validation
        client, _ = _admin_client()
        csv_bytes = _make_csv([row])
        file_obj = io.BytesIO(csv_bytes)
        file_obj.name = "tenders.csv"

        with override_settings(SIMPLE_JWT=_BASE_JWT):
            resp = client.post(UPLOAD_URL, {"file": file_obj}, format="multipart")

        assert resp.status_code == 200, (
            f"Expected HTTP 200, got {resp.status_code}: {resp.data}"
        )
        assert resp.data["accepted"] == 1, (
            f"Expected 1 accepted row, got {resp.data['accepted']}. "
            f"Rejected: {resp.data.get('rejected_rows')}"
        )
        assert resp.data["rejected"] == 0, (
            f"Expected 0 rejected rows, got {resp.data['rejected']}: "
            f"{resp.data.get('rejected_rows')}"
        )
        # Verify the record was actually persisted
        assert Tender.objects.filter(tender_id=row["tender_id"]).exists(), (
            f"Tender {row['tender_id']} was reported accepted but not found in DB"
        )

    @given(invalid_tender_row())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_invalid_row_is_rejected_with_reason(self, row_and_missing):
        # Feature: tender-shield, Property 4: CSV Schema Validation
        row, missing_fields = row_and_missing
        client, _ = _admin_client()
        csv_bytes = _make_csv([row])
        file_obj = io.BytesIO(csv_bytes)
        file_obj.name = "tenders.csv"

        with override_settings(SIMPLE_JWT=_BASE_JWT):
            resp = client.post(UPLOAD_URL, {"file": file_obj}, format="multipart")

        assert resp.status_code == 200, (
            f"Expected HTTP 200, got {resp.status_code}: {resp.data}"
        )
        assert resp.data["accepted"] == 0, (
            f"Expected 0 accepted rows for row missing {missing_fields}, "
            f"got {resp.data['accepted']}"
        )
        assert resp.data["rejected"] == 1, (
            f"Expected 1 rejected row, got {resp.data['rejected']}"
        )
        rejected = resp.data["rejected_rows"]
        assert len(rejected) == 1, f"Expected 1 entry in rejected_rows, got {len(rejected)}"
        assert rejected[0].get("reason"), (
            f"Rejected row must include a 'reason' field, got: {rejected[0]}"
        )


# ---------------------------------------------------------------------------
# Property 5 — Bid Record Acceptance
# Feature: tender-shield, Property 5: Bid Record Acceptance
# ---------------------------------------------------------------------------

_bid_counter = {"n": 0}


@st.composite
def valid_bid_record(draw, tender_id: str):
    """Generate a complete, valid bid record dict."""
    _bid_counter["n"] += 1
    return {
        "bid_id": f"BID-PBT5-{_bid_counter['n']}",
        "tender_id": tender_id,
        "bidder_id": f"BIDR-PBT5-{draw(st.integers(min_value=1, max_value=9999))}",
        "bidder_name": draw(_safe_text),
        "bid_amount": str(draw(st.decimals(min_value=Decimal("1.00"), max_value=Decimal("1e10"),
                                           allow_nan=False, allow_infinity=False, places=2))),
        "submission_timestamp": "2030-12-30T10:00:00Z",
    }


class BidRecordAcceptanceTest(TestCase):
    """
    Property 5: For any bid record with all required fields, the record is
    accepted and stored.
    Validates: Requirements 2.4
    """

    def setUp(self):
        # Create a tender that bids can reference
        self.tender = Tender.objects.create(
            tender_id="T-PBT5-BASE",
            title="PBT5 Base Tender",
            category="IT",
            estimated_value=Decimal("500000.00"),
            currency="INR",
            submission_deadline="2030-12-31T23:59:59Z",
            buyer_id="BUYER-PBT5",
            buyer_name="PBT5 Buyer",
        )

    @given(st.data())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_valid_bid_is_accepted_and_stored(self, data):
        # Feature: tender-shield, Property 5: Bid Record Acceptance
        bid_data = data.draw(valid_bid_record(tender_id=self.tender.tender_id))
        client, _ = _admin_client()

        with override_settings(SIMPLE_JWT=_BASE_JWT), \
             patch("bids.views._enqueue_pipeline"):
            resp = client.post(BID_URL, bid_data, format="json")

        assert resp.status_code == 201, (
            f"Expected HTTP 201, got {resp.status_code}: {resp.data}"
        )
        assert Bid.objects.filter(bid_id=bid_data["bid_id"]).exists(), (
            f"Bid {bid_data['bid_id']} was reported accepted but not found in DB"
        )
        # Verify the bidder was upserted
        assert Bidder.objects.filter(bidder_id=bid_data["bidder_id"]).exists(), (
            f"Bidder {bid_data['bidder_id']} was not created/upserted"
        )


# ---------------------------------------------------------------------------
# Property 6 — Duplicate Tender Rejection Preserves Original
# Feature: tender-shield, Property 6: Duplicate Tender Rejection Preserves Original
# ---------------------------------------------------------------------------

_dup_counter = {"n": 0}


@st.composite
def tender_pair(draw):
    """Generate an original tender row and a duplicate with the same tender_id."""
    _dup_counter["n"] += 1
    shared_id = f"T-PBT6-{_dup_counter['n']}"
    original = {
        "tender_id": shared_id,
        "title": draw(_safe_text),
        "category": draw(_safe_text),
        "estimated_value": str(draw(st.decimals(min_value=Decimal("1.00"), max_value=Decimal("1e12"),
                                                allow_nan=False, allow_infinity=False, places=2))),
        "currency": draw(st.sampled_from(["INR", "USD", "EUR"])),
        "submission_deadline": "2030-12-31T23:59:59Z",
        "buyer_id": draw(_safe_text),
        "buyer_name": draw(_safe_text),
    }
    duplicate = {
        **original,
        # Different title/buyer to confirm the original is preserved, not overwritten
        "title": draw(_safe_text),
        "buyer_name": draw(_safe_text),
    }
    return original, duplicate


class DuplicateTenderRejectionTest(TestCase):
    """
    Property 6: For any existing tender, submitting a new record with the same
    tender_id is rejected and the original record remains unchanged.
    Validates: Requirements 2.5
    """

    @given(tender_pair())
    @settings(max_examples=100, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_duplicate_tender_id_rejected_and_original_preserved(self, pair):
        # Feature: tender-shield, Property 6: Duplicate Tender Rejection Preserves Original
        original, duplicate = pair
        client, _ = _admin_client()

        # Upload the original via CSV
        csv_original = _make_csv([original])
        file_obj = io.BytesIO(csv_original)
        file_obj.name = "original.csv"

        with override_settings(SIMPLE_JWT=_BASE_JWT):
            resp1 = client.post(UPLOAD_URL, {"file": file_obj}, format="multipart")

        assert resp1.status_code == 200, f"Original upload failed: {resp1.data}"
        assert resp1.data["accepted"] == 1, (
            f"Expected original to be accepted, got: {resp1.data}"
        )

        # Capture the original record's state from DB
        original_record = Tender.objects.get(tender_id=original["tender_id"])
        original_title = original_record.title
        original_buyer = original_record.buyer_name

        # Attempt to upload the duplicate
        csv_dup = _make_csv([duplicate])
        file_obj2 = io.BytesIO(csv_dup)
        file_obj2.name = "duplicate.csv"

        with override_settings(SIMPLE_JWT=_BASE_JWT):
            resp2 = client.post(UPLOAD_URL, {"file": file_obj2}, format="multipart")

        assert resp2.status_code == 200, f"Duplicate upload request failed: {resp2.data}"
        assert resp2.data["accepted"] == 0, (
            f"Duplicate tender_id should be rejected, but was accepted: {resp2.data}"
        )
        assert resp2.data["rejected"] == 1, (
            f"Expected 1 rejected row for duplicate, got {resp2.data['rejected']}"
        )
        rejected = resp2.data["rejected_rows"]
        assert len(rejected) == 1
        assert rejected[0].get("reason"), (
            f"Rejected duplicate must include a 'reason', got: {rejected[0]}"
        )

        # Verify the original record is unchanged
        original_record.refresh_from_db()
        assert original_record.title == original_title, (
            f"Original title was overwritten: expected '{original_title}', "
            f"got '{original_record.title}'"
        )
        assert original_record.buyer_name == original_buyer, (
            f"Original buyer_name was overwritten: expected '{original_buyer}', "
            f"got '{original_record.buyer_name}'"
        )

        # Confirm only one record exists for this tender_id
        count = Tender.objects.filter(tender_id=original["tender_id"]).count()
        assert count == 1, (
            f"Expected exactly 1 record for tender_id '{original['tender_id']}', found {count}"
        )
