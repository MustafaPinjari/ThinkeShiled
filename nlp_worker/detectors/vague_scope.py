"""
VagueScopeDetector — detects intentionally vague tender specifications using
text statistics relative to contract value.

The pure ``compute_vagueness_score`` function is the testable unit; the
``detect`` method adds DB baseline lookup and returns a ``DetectionResult``.

Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
"""

from __future__ import annotations

import logging
from decimal import Decimal
from math import log2

import numpy as np

from nlp_worker.detectors import DetectionResult

logger = logging.getLogger(__name__)


def compute_vagueness_score(
    spec_text: str,
    estimated_value: Decimal,
    category: str,
    category_baseline: float = 0.70,
) -> float:
    """Compute a composite vagueness score for a tender specification.

    The score is derived from three signals:
    - **Type-token ratio (TTR)**: low TTR indicates repetitive/generic language.
    - **Shannon entropy**: low entropy indicates few distinct concepts.
    - **Value-normalised length**: a high-value contract with a very short spec
      is suspicious.

    Formula (from design doc)::

        raw_score = (
            (1.0 - min(ttr, 1.0)) * 0.35
            + (1.0 - min(entropy / 10.0, 1.0)) * 0.35
            + (1.0 - min(value_normalized_length / 100.0, 1.0)) * 0.30
        )
        vagueness_score = clamp(raw_score, 0.0, 1.0)

    Args:
        spec_text: Raw specification text (caller guarantees non-empty).
        estimated_value: Contract value in the local currency unit.
        category: Procurement category (unused in computation; kept for
            signature consistency with the ``detect`` method).
        category_baseline: Unused in this pure function; present so callers
            can pass it through for logging purposes.

    Returns:
        Float in ``[0.0, 1.0]``; higher values indicate vaguer specifications.
    """
    words = spec_text.lower().split()
    word_count = len(words)

    if word_count == 0:
        return 0.0

    # Type-token ratio
    ttr = len(set(words)) / word_count

    # Shannon entropy of word frequency distribution
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    freq_dist = {w: count / word_count for w, count in freq.items()}
    entropy = -sum(p * log2(p) for p in freq_dist.values() if p > 0)

    # Value-normalised length
    value_normalized_length = word_count / (float(estimated_value) / 100_000 + 1)

    raw_score = (
        (1.0 - min(ttr, 1.0)) * 0.35
        + (1.0 - min(entropy / 10.0, 1.0)) * 0.35
        + (1.0 - min(value_normalized_length / 100.0, 1.0)) * 0.30
    )

    return float(max(0.0, min(raw_score, 1.0)))


class VagueScopeDetector:
    """Detect vague tender specifications using text-statistical heuristics.

    Args:
        default_baseline: Fallback vagueness threshold when no per-category
            historical data is available (default 0.70).
    """

    def __init__(self, default_baseline: float = 0.70) -> None:
        self._default_baseline = default_baseline

    # ------------------------------------------------------------------
    # DB baseline lookup (lazy Django import to avoid non-Django contexts)
    # ------------------------------------------------------------------

    def _get_category_baseline(self, category: str) -> float:
        """Return the 95th-percentile vagueness score for the category from DB.

        Falls back to ``self._default_baseline`` if fewer than 20 historical
        scores exist or if any import/DB error occurs.
        """
        try:
            import django  # noqa: F401 — ensure Django is set up
            from nlp.models import SpecAnalysisResult

            scores = list(
                SpecAnalysisResult.objects.filter(
                    tender__category=category,
                    vagueness_score__isnull=False,
                ).values_list("vagueness_score", flat=True)
            )
            if len(scores) >= 20:
                return float(np.percentile(scores, 95))
        except Exception:
            pass
        return self._default_baseline

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        tender_id: int,
        spec_text: str,
        estimated_value: Decimal,
        category: str,
    ) -> DetectionResult | None:
        """Compute vagueness score and return a result if it exceeds the baseline.

        Args:
            tender_id: Primary key of the tender being analysed.
            spec_text: Raw specification text (non-empty; caller guarantees this).
            estimated_value: Contract value in the local currency unit.
            category: Procurement category used for per-category baseline lookup.

        Returns:
            :class:`DetectionResult` with ``flag_type="SPEC_VAGUE_SCOPE"`` if
            ``vagueness_score > category_baseline``, otherwise ``None``.
        """
        words = spec_text.lower().split()
        word_count = len(words)

        if word_count == 0:
            logger.debug(
                "VagueScopeDetector: empty spec_text for tender_id=%d, skipping.",
                tender_id,
            )
            return None

        # Recompute intermediate values for trigger_data
        ttr = len(set(words)) / word_count

        freq: dict[str, int] = {}
        for w in words:
            freq[w] = freq.get(w, 0) + 1
        freq_dist = {w: count / word_count for w, count in freq.items()}
        entropy = -sum(p * log2(p) for p in freq_dist.values() if p > 0)

        value_normalized_length = word_count / (float(estimated_value) / 100_000 + 1)

        vagueness_score = compute_vagueness_score(spec_text, estimated_value, category)

        baseline = self._get_category_baseline(category)

        if vagueness_score <= baseline:
            logger.debug(
                "VagueScopeDetector: score %.4f <= baseline %.4f for tender_id=%d.",
                vagueness_score,
                baseline,
                tender_id,
            )
            return None

        logger.info(
            "VagueScopeDetector: SPEC_VAGUE_SCOPE flagged for tender_id=%d "
            "(score=%.4f, baseline=%.4f).",
            tender_id,
            vagueness_score,
            baseline,
        )

        return DetectionResult(
            flag_type="SPEC_VAGUE_SCOPE",
            severity="MEDIUM",
            score=vagueness_score,
            trigger_data={
                "vagueness_score": vagueness_score,
                "word_count": word_count,
                "type_token_ratio": ttr,
                "entropy": entropy,
                "value_normalized_length": value_normalized_length,
                "category_baseline": baseline,
            },
        )
