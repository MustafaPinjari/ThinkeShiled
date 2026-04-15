"""
TailoringDetector — detects specification tailoring by comparing a tender's
embedding against the known-fraud corpus in Qdrant.

A high cosine similarity to a previously flagged spec suggests the new spec
was written to favour the same vendor.

Requirements: 4.1, 4.2, 4.3
"""

from __future__ import annotations

import logging

import numpy as np

from nlp_worker.detectors import DetectionResult
from nlp_worker.vector_store import VectorStore

logger = logging.getLogger(__name__)


class TailoringDetector:
    """Detect specification tailoring via fraud-corpus similarity search.

    Args:
        vector_store: Qdrant-backed vector store instance.
        threshold: Minimum cosine similarity to raise a flag (default 0.85).
    """

    def __init__(self, vector_store: VectorStore, threshold: float = 0.85) -> None:
        self._vector_store = vector_store
        self._threshold = threshold

    def detect(
        self,
        tender_id: int,
        vector: np.ndarray,
        category: str,
    ) -> DetectionResult | None:
        """Search the fraud corpus and return a result if similarity >= threshold.

        Args:
            tender_id: Primary key of the tender being analysed.
            vector: L2-normalised 384-dim embedding of the full spec text.
            category: Procurement category string (passed through to trigger_data).

        Returns:
            :class:`DetectionResult` with ``flag_type="SPEC_TAILORING"`` if the
            maximum cosine similarity to any fraud-corpus entry is >= threshold,
            otherwise ``None``.
        """
        hits = self._vector_store.search_similar(
            vector=vector,
            top_k=5,
            filter_payload={"is_fraud_corpus": True},
        )

        if not hits:
            logger.debug(
                "TailoringDetector: no fraud-corpus hits for tender_id=%d.", tender_id
            )
            return None

        best_hit = hits[0]  # sorted descending by similarity

        if best_hit.similarity < self._threshold:
            logger.debug(
                "TailoringDetector: best similarity %.4f < threshold %.4f for tender_id=%d.",
                best_hit.similarity,
                self._threshold,
                tender_id,
            )
            return None

        logger.info(
            "TailoringDetector: SPEC_TAILORING flagged for tender_id=%d "
            "(similarity=%.4f, matched_tender_id=%d).",
            tender_id,
            best_hit.similarity,
            best_hit.tender_id,
        )

        return DetectionResult(
            flag_type="SPEC_TAILORING",
            severity="HIGH",
            score=best_hit.similarity,
            trigger_data={
                "matched_tender_id": best_hit.tender_id,
                "similarity_score": best_hit.similarity,
                "threshold": self._threshold,
                # Sentence-level matching is performed later by ClauseHighlighter
                "matched_sentences": [],
            },
        )
