"""
VectorStore — thin wrapper around the Qdrant client for tender spec embeddings.

Collection name: ``tender_specs``
Distance metric: Cosine
Vector dimension: 384 (from SpecEmbedder)

The collection is created automatically on first use if it does not exist.

Requirements: 10.1, 10.2, 10.3, 10.4
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

COLLECTION_NAME = "tender_specs"
VECTOR_DIM = 384
DEFAULT_QDRANT_URL = "http://qdrant:6333"


@dataclass
class SimilarityResult:
    """Result of a vector similarity search.

    Attributes:
        tender_id: Primary key of the matched tender.
        similarity: Cosine similarity score in [-1.0, 1.0]; higher is more similar.
    """

    tender_id: int
    similarity: float


class VectorStore:
    """Qdrant-backed store for tender specification embeddings.

    Wraps ``qdrant_client.QdrantClient`` and enforces:
    - Collection ``tender_specs`` with cosine distance metric (Req 10.1)
    - Payload fields: ``tender_id``, ``category``, ``is_fraud_corpus``,
      ``confirmed_fraud``, ``ingested_at`` (Req 10.2)
    - Auto-creation of the collection on first use (Req 10.3)
    - ``mark_fraud_corpus()`` updates ``is_fraud_corpus`` and
      ``confirmed_fraud`` payload fields (Req 10.4)
    """

    def __init__(self, url: Optional[str] = None) -> None:
        from qdrant_client import QdrantClient

        resolved_url = url or os.environ.get("QDRANT_URL", DEFAULT_QDRANT_URL)
        self._client = QdrantClient(url=resolved_url)
        self._collection_ready = False

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_collection(self) -> None:
        """Create the ``tender_specs`` collection if it does not exist.

        Called lazily before the first operation so that the collection is
        created on first use (Req 10.3).
        """
        if self._collection_ready:
            return

        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in self._client.get_collections().collections}
        if COLLECTION_NAME not in existing:
            logger.info(
                "Collection '%s' not found — creating with cosine distance, dim=%d.",
                COLLECTION_NAME,
                VECTOR_DIM,
            )
            self._client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )
            logger.info("Collection '%s' created.", COLLECTION_NAME)
        else:
            logger.debug("Collection '%s' already exists.", COLLECTION_NAME)

        self._collection_ready = True

    @staticmethod
    def _to_list(vector: np.ndarray) -> list[float]:
        """Convert a numpy array to a plain Python list of floats."""
        return vector.astype(float).tolist()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert(self, tender_id: int, vector: np.ndarray, payload: dict) -> None:
        """Insert or update the embedding point for a tender.

        The point ID is set to ``tender_id`` so that repeated calls for the
        same tender overwrite the previous embedding (upsert semantics).

        Args:
            tender_id: Primary key of the tender — used as the Qdrant point ID.
            vector: 384-dim L2-normalized float32 embedding vector.
            payload: Metadata dict; should include ``category``,
                ``is_fraud_corpus``, ``confirmed_fraud``, and ``ingested_at``.
                ``tender_id`` is always added/overwritten from the argument.
        """
        self._ensure_collection()

        merged_payload = dict(payload)
        merged_payload["tender_id"] = tender_id
        if "ingested_at" not in merged_payload:
            merged_payload["ingested_at"] = datetime.now(timezone.utc).isoformat()

        from qdrant_client.models import PointStruct

        self._client.upsert(
            collection_name=COLLECTION_NAME,
            points=[
                PointStruct(
                    id=tender_id,
                    vector=self._to_list(vector),
                    payload=merged_payload,
                )
            ],
        )
        logger.debug("Upserted embedding for tender_id=%d.", tender_id)

    def search_similar(
        self,
        vector: np.ndarray,
        top_k: int = 10,
        filter_payload: Optional[dict] = None,
    ) -> list[SimilarityResult]:
        """Return the top-k most similar tenders, sorted descending by score.

        Args:
            vector: Query embedding vector (384-dim, L2-normalized).
            top_k: Maximum number of results to return.
            filter_payload: Optional dict of exact-match payload filters.
                Example: ``{"is_fraud_corpus": True}`` restricts search to
                the known-fraud corpus.

        Returns:
            List of :class:`SimilarityResult` sorted by descending similarity.
        """
        self._ensure_collection()

        query_filter = None
        if filter_payload:
            from qdrant_client.models import FieldCondition, Filter, MatchValue

            conditions = [
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in filter_payload.items()
            ]
            query_filter = Filter(must=conditions)

        hits = self._client.search(
            collection_name=COLLECTION_NAME,
            query_vector=self._to_list(vector),
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )

        results = [
            SimilarityResult(
                tender_id=int(hit.payload.get("tender_id", hit.id)),
                similarity=float(hit.score),
            )
            for hit in hits
        ]
        # Qdrant returns results sorted descending by score for cosine distance;
        # enforce the contract explicitly.
        results.sort(key=lambda r: r.similarity, reverse=True)
        return results

    def mark_fraud_corpus(self, tender_id: int, confirmed_fraud: bool) -> None:
        """Update the fraud-corpus flags for a tender's embedding point.

        Sets ``is_fraud_corpus=True`` and ``confirmed_fraud=<confirmed_fraud>``
        on the payload of the point identified by ``tender_id`` (Req 10.4).

        Args:
            tender_id: Primary key of the tender whose point should be updated.
            confirmed_fraud: Whether the tender has been confirmed as fraud.
        """
        self._ensure_collection()

        from qdrant_client.models import SetPayload

        self._client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={
                "is_fraud_corpus": True,
                "confirmed_fraud": confirmed_fraud,
            },
            points=[tender_id],
        )
        logger.info(
            "Marked tender_id=%d as fraud corpus (confirmed_fraud=%s).",
            tender_id,
            confirmed_fraud,
        )
