"""
CopyPasteDetector — detects near-verbatim reuse of previously flagged or
confirmed-fraud tender specifications.

Two separate Qdrant queries are issued (``is_fraud_corpus=True`` and
``confirmed_fraud=True``) because Qdrant does not support OR filters in a
single ``must`` clause.  Results are merged, deduplicated by tender_id, and
the highest similarity is used for threshold comparison.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
"""

from __future__ import annotations

import logging

import numpy as np

from nlp_worker.detectors import DetectionResult
from nlp_worker.vector_store import VectorStore, SimilarityResult

logger = logging.getLogger(__name__)


class CopyPasteDetector:
    """Detect copy-paste fraud via dual fraud-corpus similarity search.

    Args:
        vector_store: Qdrant-backed vector store instance.
        threshold: Minimum cosine similarity to raise a flag (default 0.92).
    """

    def __init__(self, vector_store: VectorStore, threshold: float = 0.92) -> None:
        self._vector_store = vector_store
        self._threshold = threshold

    def detect(
        self,
        tender_id: int,
        vector: np.ndarray,
    ) -> DetectionResult | None:
        """Search fraud corpus (two queries) and return a result if similarity >= threshold.

        Args:
            tender_id: Primary key of the tender being analysed.
            vector: L2-normalised 384-dim embedding of the full spec text.

        Returns:
            :class:`DetectionResult` with ``flag_type="SPEC_COPY_PASTE"`` if the
            maximum cosine similarity across both queries is >= threshold,
            otherwise ``None``.
        """
        # Query 1: is_fraud_corpus entries
        hits_fraud = self._vector_store.search_similar(
            vector=vector,
            top_k=10,
            filter_payload={"is_fraud_corpus": True},
        )

        # Query 2: confirmed_fraud entries
        hits_confirmed = self._vector_store.search_similar(
            vector=vector,
            top_k=10,
            filter_payload={"confirmed_fraud": True},
        )

        # Merge and deduplicate by tender_id, keeping the highest similarity per id
        best_by_id: dict[int, SimilarityResult] = {}
        for hit in hits_fraud + hits_confirmed:
            existing = best_by_id.get(hit.tender_id)
            if existing is None or hit.similarity > existing.similarity:
                best_by_id[hit.tender_id] = hit

        if not best_by_id:
            logger.debug(
                "CopyPasteDetector: no corpus hits for tender_id=%d.", tender_id
            )
            return None

        best_hit = max(best_by_id.values(), key=lambda r: r.similarity)

        if best_hit.similarity < self._threshold:
            logger.debug(
                "CopyPasteDetector: best similarity %.4f < threshold %.4f for tender_id=%d.",
                best_hit.similarity,
                self._threshold,
                tender_id,
            )
            return None

        logger.info(
            "CopyPasteDetector: SPEC_COPY_PASTE flagged for tender_id=%d "
            "(similarity=%.4f, matched_tender_id=%d).",
            tender_id,
            best_hit.similarity,
            best_hit.tender_id,
        )

        return DetectionResult(
            flag_type="SPEC_COPY_PASTE",
            severity="HIGH",
            score=best_hit.similarity,
            trigger_data={
                "matched_tender_id": best_hit.tender_id,
                "similarity_score": best_hit.similarity,
                "threshold": self._threshold,
            },
        )
