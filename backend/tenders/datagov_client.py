"""
data.gov.in OGD API client for GeM procurement data.

The Open Government Data (OGD) Platform India exposes GeM datasets via a
REST API. Each dataset has a resource_id. You need a free API key from:
    https://data.gov.in/user/register  →  Dashboard → My Account → Generate Key

API format:
    GET https://api.data.gov.in/resource/{resource_id}
        ?api-key={key}
        &format=json
        &offset={offset}
        &limit={limit}
        &filters[field]=value

Known GeM resource IDs on data.gov.in:
    - 6176b5b4-2b3e-4e8e-b1e2-3c4d5e6f7a8b  (GeM Orders — illustrative)

Because data.gov.in resource IDs change when datasets are updated, this
client accepts the resource_id as a parameter so you can swap it without
touching code. Pass it via the management command --resource-id flag or
set DATAGOV_RESOURCE_ID in .env.
"""

import logging
import time
from typing import Iterator

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.data.gov.in/resource/{resource_id}"
DEFAULT_PAGE_SIZE = 100
MAX_RETRIES = 3
RETRY_BACKOFF = 2  # seconds


class DataGovAPIError(Exception):
    pass


class DataGovClient:
    """
    Thin wrapper around the data.gov.in OGD REST API.

    Usage:
        client = DataGovClient(api_key="your_key", resource_id="abc-123")
        for record in client.iter_records(filters={"State": "Delhi"}):
            print(record)
    """

    def __init__(self, api_key: str, resource_id: str, page_size: int = DEFAULT_PAGE_SIZE):
        if not api_key:
            raise DataGovAPIError(
                "DATAGOV_API_KEY is not set. "
                "Register at https://data.gov.in/user/register and generate a key."
            )
        if not resource_id:
            raise DataGovAPIError(
                "DATAGOV_RESOURCE_ID is not set. "
                "Find the resource ID on the dataset page at data.gov.in."
            )
        self.api_key = api_key
        self.resource_id = resource_id
        self.page_size = page_size
        self.url = BASE_URL.format(resource_id=resource_id)

    def _get(self, offset: int, filters: dict | None = None) -> dict:
        params = {
            "api-key": self.api_key,
            "format": "json",
            "offset": offset,
            "limit": self.page_size,
        }
        if filters:
            for field, value in filters.items():
                params[f"filters[{field}]"] = value

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = requests.get(self.url, params=params, timeout=30)
                if resp.status_code == 401:
                    raise DataGovAPIError("Invalid API key. Check DATAGOV_API_KEY in .env.")
                if resp.status_code == 404:
                    raise DataGovAPIError(
                        f"Resource {self.resource_id} not found. "
                        "Verify DATAGOV_RESOURCE_ID on data.gov.in."
                    )
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == MAX_RETRIES:
                    raise DataGovAPIError(f"API request failed after {MAX_RETRIES} attempts: {exc}") from exc
                logger.warning("Attempt %d failed: %s — retrying in %ds", attempt, exc, RETRY_BACKOFF)
                time.sleep(RETRY_BACKOFF * attempt)

    def iter_records(self, filters: dict | None = None) -> Iterator[dict]:
        """Yield every record from the dataset, paginating automatically."""
        offset = 0
        total = None

        while True:
            data = self._get(offset, filters)

            # data.gov.in response shape:
            # { "status": "ok", "total": 12345, "count": 100, "records": [...] }
            if data.get("status") != "ok":
                raise DataGovAPIError(f"Unexpected API status: {data.get('status')}")

            records = data.get("records", [])
            if total is None:
                total = int(data.get("total", 0))
                logger.info("Total records available: %d", total)

            if not records:
                break

            yield from records

            offset += len(records)
            if offset >= total:
                break

            # Be polite — don't hammer the government API
            time.sleep(0.2)

    def fetch_sample(self, limit: int = 10) -> list[dict]:
        """Fetch a small sample to inspect field names before a full import."""
        data = self._get(offset=0)
        data["records"] = data.get("records", [])[:limit]
        return data["records"]
