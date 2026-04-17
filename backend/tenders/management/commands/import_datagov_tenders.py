"""
Management command: import_datagov_tenders

Fetches real GeM/CPPP procurement data from the data.gov.in OGD API and
imports it into TenderShield's Tender + Bidder + Bid models.

Prerequisites
─────────────
1. Register at https://data.gov.in/user/register
2. Go to Dashboard → My Account → Generate Key
3. Add to .env:
       DATAGOV_API_KEY=your_40_char_key_here
       DATAGOV_RESOURCE_ID=the_resource_id_from_dataset_page

Finding the resource ID
───────────────────────
Go to https://data.gov.in and search for "GeM procurement" or "CPPP tenders".
Open a dataset. The resource ID is in the URL:
    https://data.gov.in/resource/{resource_id}
or shown in the "Catalog API" section of the dataset page.

Example datasets (IDs may change when datasets are updated):
    - GeM Orders Data: search "gem orders" on data.gov.in
    - CPPP Tender Results: search "cppp result tenders" on data.gov.in

Usage
─────
# Dry run — print what would be imported without saving
python manage.py import_datagov_tenders --dry-run

# Import up to 500 records
python manage.py import_datagov_tenders --limit 500

# Import with a specific resource ID (overrides .env)
python manage.py import_datagov_tenders --resource-id abc-123-def

# Filter by state
python manage.py import_datagov_tenders --filter "State=Maharashtra"

# Inspect field names before importing (prints first 3 records as JSON)
python manage.py import_datagov_tenders --inspect

Field Mapping
─────────────
data.gov.in GeM datasets use different column names depending on the dataset.
Run --inspect first to see the actual field names, then adjust FIELD_MAP below
to match. The defaults cover the most common GeM Orders dataset schema.
"""

import json
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.utils import timezone

from tenders.datagov_client import DataGovClient, DataGovAPIError
from tenders.models import Tender, TenderStatus
from bids.models import Bidder, Bid

logger = logging.getLogger(__name__)


# ── Field mapping ─────────────────────────────────────────────────────────────
# Maps data.gov.in column names → TenderShield model fields.
# Run --inspect to see the actual column names for your dataset, then update
# this map. Keys are data.gov.in field names (case-sensitive).

FIELD_MAP = {
    # Tender fields
    "tender_id":        ["Bid Number", "Tender ID", "BidNumber", "tender_id", "Order Number"],
    "title":            ["Tender Title", "Title", "Item Description", "Product Name", "tender_title"],
    "category":         ["Product Category", "Category", "Item Category", "category"],
    "estimated_value":  ["Tender Value (INR)", "Estimated Value", "Order Value", "Total Order Value", "tender_value"],
    "buyer_name":       ["Organisation Name", "Buyer Name", "Ministry/Department", "buyer_name"],
    "buyer_id":         ["Organisation ID", "Buyer ID", "Ministry Code", "buyer_id"],
    "deadline":         ["Bid Submission End Date", "Submission Deadline", "Closing Date", "bid_end_date"],
    "publication_date": ["Bid Document Download Start Date", "Published Date", "Start Date", "published_date"],
    "status":           ["Bid Status", "Status", "Tender Status", "status"],

    # Bidder / winner fields (present in result/order datasets)
    "winner_name":      ["Seller Name", "L1 Bidder Name", "Winner Name", "Awarded To", "seller_name"],
    "winner_id":        ["Seller ID", "L1 Bidder ID", "Winner ID", "seller_id"],
    "winner_address":   ["Seller Address", "Registered Address", "seller_address"],
    "winning_bid":      ["Order Value", "L1 Bid Amount", "Winning Bid Amount", "order_value"],
}

STATUS_MAP = {
    "active":    TenderStatus.ACTIVE,
    "open":      TenderStatus.ACTIVE,
    "live":      TenderStatus.ACTIVE,
    "closed":    TenderStatus.CLOSED,
    "awarded":   TenderStatus.AWARDED,
    "completed": TenderStatus.AWARDED,
    "cancelled": TenderStatus.CANCELLED,
    "withdrawn": TenderStatus.CANCELLED,
}


def _pick(record: dict, candidates: list[str], default=None):
    """Return the first matching field value from a record."""
    for key in candidates:
        if key in record and record[key] not in (None, "", "N/A", "NA", "-"):
            return record[key]
    return default


def _parse_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        cleaned = str(value).replace(",", "").replace("₹", "").replace("INR", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    formats = [
        "%d-%b-%Y %I:%M %p",   # 15-Jan-2024 03:00 PM
        "%d/%m/%Y %H:%M:%S",   # 15/01/2024 15:00:00
        "%d/%m/%Y",            # 15/01/2024
        "%Y-%m-%d %H:%M:%S",   # 2024-01-15 15:00:00
        "%Y-%m-%dT%H:%M:%S",   # 2024-01-15T15:00:00
        "%Y-%m-%d",            # 2024-01-15
        "%d-%m-%Y",            # 15-01-2024
        "%d %b %Y",            # 15 Jan 2024
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(str(value).strip(), fmt)
            return dt.replace(tzinfo=dt_timezone.utc)
        except ValueError:
            continue
    logger.debug("Could not parse date: %r", value)
    return None


def _parse_status(value) -> str:
    if not value:
        return TenderStatus.ACTIVE
    return STATUS_MAP.get(str(value).lower().strip(), TenderStatus.ACTIVE)


class Command(BaseCommand):
    help = "Import GeM/CPPP tender data from data.gov.in OGD API into TenderShield"

    def add_arguments(self, parser):
        parser.add_argument(
            "--resource-id",
            type=str,
            default=None,
            help="data.gov.in resource ID (overrides DATAGOV_RESOURCE_ID in .env)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Maximum records to import (0 = all)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be imported without saving to the database",
        )
        parser.add_argument(
            "--inspect",
            action="store_true",
            help="Print the first 3 raw records as JSON and exit (use to discover field names)",
        )
        parser.add_argument(
            "--filter",
            type=str,
            action="append",
            dest="filters",
            metavar="FIELD=VALUE",
            help="Filter records (e.g. --filter 'State=Maharashtra'). Repeatable.",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            default=True,
            help="Skip tenders that already exist in the database (default: True)",
        )
        parser.add_argument(
            "--run-detection",
            action="store_true",
            help="Run fraud detection engine on imported tenders after import",
        )

    def handle(self, *args, **options):
        api_key = getattr(settings, "DATAGOV_API_KEY", None)
        resource_id = options["resource_id"] or getattr(settings, "DATAGOV_RESOURCE_ID", None)

        try:
            client = DataGovClient(api_key=api_key, resource_id=resource_id)
        except DataGovAPIError as exc:
            raise CommandError(str(exc)) from exc

        # ── Inspect mode ──────────────────────────────────────────────────────
        if options["inspect"]:
            self.stdout.write("Fetching sample records to inspect field names...\n")
            try:
                sample = client.fetch_sample(limit=3)
            except DataGovAPIError as exc:
                raise CommandError(str(exc)) from exc

            if not sample:
                self.stdout.write(self.style.WARNING("No records returned. Check resource ID."))
                return

            self.stdout.write(self.style.SUCCESS(f"Found {len(sample)} sample records:\n"))
            for i, record in enumerate(sample, 1):
                self.stdout.write(f"\n── Record {i} ──")
                self.stdout.write(json.dumps(record, indent=2, ensure_ascii=False))
            self.stdout.write(
                "\n\nUpdate FIELD_MAP in import_datagov_tenders.py to match these field names."
            )
            return

        # ── Parse filters ─────────────────────────────────────────────────────
        filters = {}
        for f in (options["filters"] or []):
            if "=" not in f:
                raise CommandError(f"Invalid filter format: {f!r}. Use FIELD=VALUE.")
            key, _, value = f.partition("=")
            filters[key.strip()] = value.strip()

        # ── Import ────────────────────────────────────────────────────────────
        dry_run = options["dry_run"]
        limit = options["limit"]
        skip_existing = options["skip_existing"]
        run_detection = options["run_detection"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN — no data will be saved.\n"))

        stats = {"created": 0, "skipped": 0, "errors": 0, "bidders": 0, "bids": 0}

        try:
            records = client.iter_records(filters=filters)
        except DataGovAPIError as exc:
            raise CommandError(str(exc)) from exc

        tender_ids_for_detection = []

        for i, record in enumerate(records):
            if limit and i >= limit:
                break

            try:
                tender_id = _pick(record, FIELD_MAP["tender_id"])
                if not tender_id:
                    logger.debug("Skipping record with no tender_id: %r", record)
                    stats["errors"] += 1
                    continue

                tender_id = str(tender_id).strip()

                if skip_existing and Tender.objects.filter(tender_id=tender_id).exists():
                    stats["skipped"] += 1
                    continue

                title = _pick(record, FIELD_MAP["title"]) or "Untitled Tender"
                category = _pick(record, FIELD_MAP["category"]) or "General"
                estimated_value = _parse_decimal(_pick(record, FIELD_MAP["estimated_value"])) or Decimal("0")
                buyer_name = _pick(record, FIELD_MAP["buyer_name"]) or "Unknown Organisation"
                buyer_id = _pick(record, FIELD_MAP["buyer_id"]) or f"ORG-{buyer_name[:20].upper().replace(' ', '-')}"
                deadline = _parse_datetime(_pick(record, FIELD_MAP["deadline"])) or timezone.now()
                pub_date = _parse_datetime(_pick(record, FIELD_MAP["publication_date"]))
                status = _parse_status(_pick(record, FIELD_MAP["status"]))

                if dry_run:
                    self.stdout.write(
                        f"  [DRY RUN] Would import: {tender_id} | {title[:60]} | "
                        f"₹{estimated_value:,.0f} | {buyer_name[:40]} | {status}"
                    )
                    stats["created"] += 1
                    continue

                tender, created = Tender.objects.update_or_create(
                    tender_id=tender_id,
                    defaults={
                        "title": str(title)[:500],
                        "category": str(category)[:255],
                        "estimated_value": estimated_value,
                        "currency": "INR",
                        "submission_deadline": deadline,
                        "publication_date": pub_date,
                        "buyer_id": str(buyer_id)[:255],
                        "buyer_name": str(buyer_name)[:500],
                        "status": status,
                    },
                )

                if created:
                    stats["created"] += 1
                    tender_ids_for_detection.append(tender.id)
                else:
                    stats["skipped"] += 1

                # ── Import winner as bidder + bid (if present in dataset) ────
                winner_name = _pick(record, FIELD_MAP["winner_name"])
                if winner_name and created:
                    winner_id = _pick(record, FIELD_MAP["winner_id"]) or f"SELLER-{str(winner_name)[:20].upper().replace(' ', '-')}"
                    winner_address = _pick(record, FIELD_MAP["winner_address"]) or ""
                    winning_bid = _parse_decimal(_pick(record, FIELD_MAP["winning_bid"])) or estimated_value

                    bidder, bidder_created = Bidder.objects.get_or_create(
                        bidder_id=str(winner_id)[:255],
                        defaults={
                            "bidder_name": str(winner_name)[:500],
                            "registered_address": str(winner_address)[:1000],
                        },
                    )
                    if bidder_created:
                        stats["bidders"] += 1

                    bid_id = f"BID-{tender_id}-W1"
                    if not Bid.objects.filter(bid_id=bid_id).exists():
                        Bid.objects.create(
                            bid_id=bid_id,
                            tender=tender,
                            bidder=bidder,
                            bid_amount=winning_bid,
                            submission_timestamp=deadline,
                            is_winner=True,
                        )
                        stats["bids"] += 1

            except Exception as exc:
                logger.exception("Error processing record %d: %s", i, exc)
                stats["errors"] += 1
                continue

            if (i + 1) % 100 == 0:
                self.stdout.write(f"  Processed {i + 1} records...")

        # ── Run detection on new tenders ──────────────────────────────────────
        if run_detection and tender_ids_for_detection and not dry_run:
            self.stdout.write(f"\nRunning fraud detection on {len(tender_ids_for_detection)} new tenders...")
            try:
                from detection.engine import DetectionEngine
                engine = DetectionEngine()
                for tid in tender_ids_for_detection:
                    try:
                        tender = Tender.objects.get(id=tid)
                        engine.run(tender)
                    except Exception as exc:
                        logger.warning("Detection failed for tender %d: %s", tid, exc)
            except ImportError:
                self.stdout.write(self.style.WARNING("Detection engine not available — skipping."))

        # ── Summary ───────────────────────────────────────────────────────────
        self.stdout.write("\n" + "─" * 50)
        self.stdout.write(self.style.SUCCESS(
            f"Import complete:\n"
            f"  Tenders created : {stats['created']}\n"
            f"  Tenders skipped : {stats['skipped']} (already exist)\n"
            f"  Bidders created : {stats['bidders']}\n"
            f"  Bids created    : {stats['bids']}\n"
            f"  Errors          : {stats['errors']}"
        ))

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run complete — nothing was saved."))
