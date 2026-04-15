"""
UnusualRestrictionDetector — detects statistically anomalous clauses within a
tender specification by comparing each sentence's embedding against the
centroid of the tender's own sentence embeddings.

Sentences whose cosine distance from the centroid exceeds the 95th-percentile
threshold of all intra-spec distances are flagged as unusual restrictions
(e.g. brand-specific requirements, narrow geographic restrictions, non-standard
certifications).

Requirements: 7.1, 7.2, 7.4
"""

from __future__ import annotations

import logging

import numpy as np

from nlp_worker.detectors import DetectionResult
from nlp_worker.vector_store import VectorStore

logger = logging.getLogger(__name__)

_MIN_SENTENCES = 3  # need at least this many sentences for meaningful statistics


class UnusualRestrictionDetector:
    """Detect anomalous clauses via intra-spec cosine-distance outlier analysis.

    Args:
        vector_store: Qdrant-backed vector store instance (reserved for future
            cross-tender centroid computation; not used in the current
            self-referential approach).
        percentile: Distance percentile used as the anomaly threshold
            (default 95.0).
    """

    def __init__(
        self, vector_store: VectorStore, percentile: float = 95.0
    ) -> None:
        self._vector_store = vector_store
        self._percentile = percentile

    @staticmethod
    def _cosine_distance(a: np.ndarray, b: np.ndarray) -> float:
        """Return cosine distance (1 - cosine_similarity) between two vectors.

        Both vectors are assumed to be L2-normalised, so the dot product equals
        the cosine similarity.
        """
        similarity = float(np.dot(a, b))
        # Clamp to [-1, 1] to guard against floating-point drift
        similarity = max(-1.0, min(1.0, similarity))
        return 1.0 - similarity

    def detect(
        self,
        tender_id: int,
        sentences: list[tuple[str, np.ndarray]],
        category: str,
    ) -> DetectionResult | None:
        """Flag sentences that are outliers within the spec's own embedding space.

        Algorithm:
        1. Compute the centroid as the mean of all sentence embeddings.
        2. Compute each sentence's cosine distance from the centroid.
        3. Determine the ``percentile``-th distance as the anomaly threshold.
        4. Collect sentences whose distance exceeds the threshold.
        5. Return a ``DetectionResult`` if any anomalous sentences are found.

        Args:
            tender_id: Primary key of the tender being analysed.
            sentences: List of ``(sentence_text, embedding_vector)`` tuples
                produced by ``SpecEmbedder.embed_sentences()``.
            category: Procurement category (reserved for future cross-tender
                centroid lookup; not used in current implementation).

        Returns:
            :class:`DetectionResult` with ``flag_type="SPEC_UNUSUAL_RESTRICTION"``
            if anomalous sentences are found and ``len(sentences) >= 3``,
            otherwise ``None``.
        """
        if len(sentences) < _MIN_SENTENCES:
            logger.debug(
                "UnusualRestrictionDetector: only %d sentence(s) for tender_id=%d "
                "(minimum %d required), skipping.",
                len(sentences),
                tender_id,
                _MIN_SENTENCES,
            )
            return None

        texts = [s for s, _ in sentences]
        vectors = np.stack([v for _, v in sentences])  # shape: (N, 384)

        # Centroid = mean of all sentence embeddings
        centroid = vectors.mean(axis=0)

        # Cosine distances from centroid
        distances = np.array(
            [self._cosine_distance(vec, centroid) for vec in vectors],
            dtype=float,
        )

        threshold = float(np.percentile(distances, self._percentile))

        anomalous_indices = [
            i for i, d in enumerate(distances) if d > threshold
        ]

        if not anomalous_indices:
            logger.debug(
                "UnusualRestrictionDetector: no anomalous sentences for tender_id=%d.",
                tender_id,
            )
            return None

        anomalous_clauses = [
            {
                "sentence_text": texts[i],
                "sentence_index": i,
                "distance": float(distances[i]),
            }
            for i in anomalous_indices
        ]

        flagged_distances = [float(distances[i]) for i in anomalous_indices]
        overall_anomaly_score = float(
            max(0.0, min(1.0, float(np.mean(flagged_distances))))
        )

        logger.info(
            "UnusualRestrictionDetector: SPEC_UNUSUAL_RESTRICTION flagged for "
            "tender_id=%d (score=%.4f, %d anomalous clause(s), threshold=%.4f).",
            tender_id,
            overall_anomaly_score,
            len(anomalous_clauses),
            threshold,
        )

        return DetectionResult(
            flag_type="SPEC_UNUSUAL_RESTRICTION",
            severity="MEDIUM",
            score=overall_anomaly_score,
            trigger_data={
                "anomalous_clauses": anomalous_clauses,
                "threshold": threshold,
                "total_sentences": len(sentences),
            },
        )
