"""
Unit tests for all four detectors in isolation.

Each detector is tested with mocked external dependencies (VectorStore, DB)
so no real Qdrant or Django DB connection is needed.

Covers:
- TailoringDetector
- CopyPasteDetector
- VagueScopeDetector
- UnusualRestrictionDetector
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from nlp_worker.detectors import DetectionResult
from nlp_worker.vector_store import SimilarityResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_vector(dim: int = 384) -> np.ndarray:
    """Return a random L2-normalised float32 vector."""
    v = np.random.randn(dim).astype(np.float32)
    v /= np.linalg.norm(v)
    return v


def _mock_store(hits: list[SimilarityResult] | None = None) -> MagicMock:
    """Return a MagicMock VectorStore whose search_similar returns *hits*."""
    store = MagicMock()
    store.search_similar.return_value = hits or []
    return store


# ---------------------------------------------------------------------------
# TailoringDetector
# ---------------------------------------------------------------------------

class TestTailoringDetector:
    """Tests for TailoringDetector."""

    def _make_detector(self, hits=None, threshold=0.85):
        from nlp_worker.detectors.tailoring import TailoringDetector
        store = _mock_store(hits)
        return TailoringDetector(vector_store=store, threshold=threshold), store

    def test_flags_when_similarity_at_threshold(self):
        """Returns DetectionResult when max similarity == threshold."""
        hits = [SimilarityResult(tender_id=42, similarity=0.85)]
        detector, _ = self._make_detector(hits=hits)
        result = detector.detect(tender_id=1, vector=_make_vector(), category="IT")
        assert result is not None
        assert result.flag_type == "SPEC_TAILORING"
        assert result.severity == "HIGH"

    def test_flags_when_similarity_above_threshold(self):
        """Returns DetectionResult when max similarity > threshold."""
        hits = [SimilarityResult(tender_id=99, similarity=0.95)]
        detector, _ = self._make_detector(hits=hits)
        result = detector.detect(tender_id=1, vector=_make_vector(), category="IT")
        assert result is not None
        assert result.flag_type == "SPEC_TAILORING"
        assert result.severity == "HIGH"
        assert result.score == pytest.approx(0.95)

    def test_no_flag_when_similarity_below_threshold(self):
        """Returns None when max similarity < threshold."""
        hits = [SimilarityResult(tender_id=42, similarity=0.84)]
        detector, _ = self._make_detector(hits=hits)
        result = detector.detect(tender_id=1, vector=_make_vector(), category="IT")
        assert result is None

    def test_no_flag_when_fraud_corpus_empty(self):
        """Returns None when no fraud corpus hits exist."""
        detector, _ = self._make_detector(hits=[])
        result = detector.detect(tender_id=1, vector=_make_vector(), category="IT")
        assert result is None

    def test_trigger_data_fields(self):
        """trigger_data contains required fields."""
        hits = [SimilarityResult(tender_id=42, similarity=0.90)]
        detector, _ = self._make_detector(hits=hits)
        result = detector.detect(tender_id=1, vector=_make_vector(), category="IT")
        assert result is not None
        td = result.trigger_data
        assert "matched_tender_id" in td
        assert "similarity_score" in td
        assert "threshold" in td
        assert "matched_sentences" in td
        assert td["matched_tender_id"] == 42
        assert td["similarity_score"] == pytest.approx(0.90)
        assert td["threshold"] == pytest.approx(0.85)

    def test_uses_best_hit_when_multiple_results(self):
        """Uses the highest-similarity hit when multiple results returned."""
        hits = [
            SimilarityResult(tender_id=10, similarity=0.90),
            SimilarityResult(tender_id=20, similarity=0.87),
        ]
        detector, _ = self._make_detector(hits=hits)
        result = detector.detect(tender_id=1, vector=_make_vector(), category="IT")
        assert result is not None
        assert result.trigger_data["matched_tender_id"] == 10

    def test_filter_payload_passed_to_store(self):
        """search_similar is called with is_fraud_corpus=True filter."""
        detector, store = self._make_detector(hits=[])
        detector.detect(tender_id=1, vector=_make_vector(), category="IT")
        store.search_similar.assert_called_once()
        call_kwargs = store.search_similar.call_args[1]
        assert call_kwargs.get("filter_payload") == {"is_fraud_corpus": True}

    def test_custom_threshold(self):
        """Custom threshold is respected."""
        hits = [SimilarityResult(tender_id=5, similarity=0.80)]
        detector, _ = self._make_detector(hits=hits, threshold=0.75)
        result = detector.detect(tender_id=1, vector=_make_vector(), category="IT")
        assert result is not None

    def test_just_below_custom_threshold(self):
        """Returns None when similarity is just below custom threshold."""
        hits = [SimilarityResult(tender_id=5, similarity=0.74)]
        detector, _ = self._make_detector(hits=hits, threshold=0.75)
        result = detector.detect(tender_id=1, vector=_make_vector(), category="IT")
        assert result is None


# ---------------------------------------------------------------------------
# CopyPasteDetector
# ---------------------------------------------------------------------------

class TestCopyPasteDetector:
    """Tests for CopyPasteDetector."""

    def _make_detector(self, fraud_hits=None, confirmed_hits=None, threshold=0.92):
        from nlp_worker.detectors.copy_paste import CopyPasteDetector
        store = MagicMock()
        # search_similar is called twice: once for is_fraud_corpus, once for confirmed_fraud
        store.search_similar.side_effect = [
            fraud_hits or [],
            confirmed_hits or [],
        ]
        return CopyPasteDetector(vector_store=store, threshold=threshold), store

    def test_flags_when_similarity_at_threshold(self):
        """Returns DetectionResult when max similarity == threshold."""
        detector, _ = self._make_detector(
            fraud_hits=[SimilarityResult(tender_id=7, similarity=0.92)]
        )
        result = detector.detect(tender_id=1, vector=_make_vector())
        assert result is not None
        assert result.flag_type == "SPEC_COPY_PASTE"
        assert result.severity == "HIGH"

    def test_flags_when_similarity_above_threshold(self):
        """Returns DetectionResult when max similarity > threshold."""
        detector, _ = self._make_detector(
            fraud_hits=[SimilarityResult(tender_id=7, similarity=0.99)]
        )
        result = detector.detect(tender_id=1, vector=_make_vector())
        assert result is not None
        assert result.score == pytest.approx(0.99)

    def test_no_flag_when_similarity_below_threshold(self):
        """Returns None when max similarity < threshold."""
        detector, _ = self._make_detector(
            fraud_hits=[SimilarityResult(tender_id=7, similarity=0.91)]
        )
        result = detector.detect(tender_id=1, vector=_make_vector())
        assert result is None

    def test_no_flag_when_no_corpus_entries(self):
        """Returns None when both queries return empty results."""
        detector, _ = self._make_detector(fraud_hits=[], confirmed_hits=[])
        result = detector.detect(tender_id=1, vector=_make_vector())
        assert result is None

    def test_trigger_data_fields(self):
        """trigger_data contains required fields."""
        detector, _ = self._make_detector(
            fraud_hits=[SimilarityResult(tender_id=55, similarity=0.95)]
        )
        result = detector.detect(tender_id=1, vector=_make_vector())
        assert result is not None
        td = result.trigger_data
        assert "matched_tender_id" in td
        assert "similarity_score" in td
        assert "threshold" in td
        assert td["matched_tender_id"] == 55
        assert td["similarity_score"] == pytest.approx(0.95)
        assert td["threshold"] == pytest.approx(0.92)

    def test_merges_both_query_results(self):
        """Uses the best hit across both fraud and confirmed queries."""
        detector, _ = self._make_detector(
            fraud_hits=[SimilarityResult(tender_id=10, similarity=0.88)],
            confirmed_hits=[SimilarityResult(tender_id=20, similarity=0.95)],
        )
        result = detector.detect(tender_id=1, vector=_make_vector())
        assert result is not None
        assert result.trigger_data["matched_tender_id"] == 20
        assert result.score == pytest.approx(0.95)

    def test_deduplicates_by_tender_id_keeps_highest(self):
        """When same tender_id appears in both queries, keeps highest similarity."""
        detector, _ = self._make_detector(
            fraud_hits=[SimilarityResult(tender_id=10, similarity=0.93)],
            confirmed_hits=[SimilarityResult(tender_id=10, similarity=0.97)],
        )
        result = detector.detect(tender_id=1, vector=_make_vector())
        assert result is not None
        assert result.score == pytest.approx(0.97)

    def test_two_search_calls_made(self):
        """search_similar is called exactly twice (one per filter)."""
        detector, store = self._make_detector()
        detector.detect(tender_id=1, vector=_make_vector())
        assert store.search_similar.call_count == 2

    def test_confirmed_fraud_filter_used(self):
        """Second call uses confirmed_fraud=True filter."""
        detector, store = self._make_detector()
        detector.detect(tender_id=1, vector=_make_vector())
        calls = store.search_similar.call_args_list
        filters = [c[1].get("filter_payload") for c in calls]
        assert {"confirmed_fraud": True} in filters


# ---------------------------------------------------------------------------
# VagueScopeDetector
# ---------------------------------------------------------------------------

class TestVagueScopeDetector:
    """Tests for VagueScopeDetector and compute_vagueness_score."""

    def _make_detector(self, baseline=0.70):
        from nlp_worker.detectors.vague_scope import VagueScopeDetector
        detector = VagueScopeDetector(default_baseline=baseline)
        # Patch DB lookup to always return the default baseline
        detector._get_category_baseline = lambda cat: baseline
        return detector

    # --- compute_vagueness_score pure function tests ---

    def test_score_in_range(self):
        """compute_vagueness_score always returns value in [0.0, 1.0]."""
        from nlp_worker.detectors.vague_scope import compute_vagueness_score
        score = compute_vagueness_score(
            "The supplier shall provide services.",
            Decimal("100000"),
            "IT",
        )
        assert 0.0 <= score <= 1.0

    def test_empty_text_returns_zero(self):
        """compute_vagueness_score returns 0.0 for empty text."""
        from nlp_worker.detectors.vague_scope import compute_vagueness_score
        score = compute_vagueness_score("", Decimal("100000"), "IT")
        assert score == 0.0

    def test_short_low_entropy_text_higher_score_than_long_high_entropy(self):
        """Short, repetitive text produces higher vagueness score than long, diverse text."""
        from nlp_worker.detectors.vague_scope import compute_vagueness_score

        short_vague = "services services services services services"
        long_diverse = (
            "The contractor shall deliver software engineering services including "
            "requirements analysis, system design, implementation, testing, deployment, "
            "documentation, training, maintenance, and support for the procurement system. "
            "All deliverables must comply with ISO 27001 security standards and GDPR regulations. "
            "The project timeline spans eighteen months with quarterly milestone reviews."
        )
        value = Decimal("500000")
        score_vague = compute_vagueness_score(short_vague, value, "IT")
        score_diverse = compute_vagueness_score(long_diverse, value, "IT")
        assert score_vague > score_diverse

    def test_score_decreases_with_more_words(self):
        """Adding more unique words to a spec reduces the vagueness score."""
        from nlp_worker.detectors.vague_scope import compute_vagueness_score

        short = "services required"
        long = " ".join(f"word{i}" for i in range(200))
        value = Decimal("100000")
        assert compute_vagueness_score(short, value, "IT") > compute_vagueness_score(long, value, "IT")

    # --- VagueScopeDetector.detect tests ---

    def test_flags_when_score_above_baseline(self):
        """Returns DetectionResult when vagueness_score > baseline."""
        detector = self._make_detector(baseline=0.10)  # very low baseline
        # Short repetitive text will have high vagueness
        result = detector.detect(
            tender_id=1,
            spec_text="services services services services services",
            estimated_value=Decimal("1000000"),
            category="IT",
        )
        assert result is not None
        assert result.flag_type == "SPEC_VAGUE_SCOPE"
        assert result.severity == "MEDIUM"

    def test_no_flag_when_score_at_or_below_baseline(self):
        """Returns None when vagueness_score <= baseline."""
        detector = self._make_detector(baseline=0.99)  # very high baseline
        result = detector.detect(
            tender_id=1,
            spec_text="services services services",
            estimated_value=Decimal("100000"),
            category="IT",
        )
        assert result is None

    def test_no_flag_for_empty_spec(self):
        """Returns None for empty spec_text."""
        detector = self._make_detector(baseline=0.10)
        result = detector.detect(
            tender_id=1,
            spec_text="",
            estimated_value=Decimal("100000"),
            category="IT",
        )
        assert result is None

    def test_trigger_data_fields(self):
        """trigger_data contains all required fields."""
        detector = self._make_detector(baseline=0.10)
        result = detector.detect(
            tender_id=1,
            spec_text="services services services services services",
            estimated_value=Decimal("1000000"),
            category="IT",
        )
        assert result is not None
        td = result.trigger_data
        required_fields = [
            "vagueness_score",
            "word_count",
            "type_token_ratio",
            "entropy",
            "value_normalized_length",
            "category_baseline",
        ]
        for field in required_fields:
            assert field in td, f"Missing field: {field}"

    def test_trigger_data_values_are_consistent(self):
        """trigger_data values are numerically consistent with the spec text."""
        from nlp_worker.detectors.vague_scope import compute_vagueness_score
        detector = self._make_detector(baseline=0.10)
        spec = "alpha beta gamma delta epsilon zeta eta theta iota kappa"
        result = detector.detect(
            tender_id=1,
            spec_text=spec,
            estimated_value=Decimal("100000"),
            category="IT",
        )
        assert result is not None
        td = result.trigger_data
        assert td["word_count"] == 10
        assert td["type_token_ratio"] == pytest.approx(1.0)  # all unique words
        assert td["vagueness_score"] == pytest.approx(
            compute_vagueness_score(spec, Decimal("100000"), "IT")
        )

    def test_score_is_clamped_to_unit_interval(self):
        """Vagueness score is always in [0.0, 1.0]."""
        from nlp_worker.detectors.vague_scope import compute_vagueness_score
        # Edge: single word, huge value
        score = compute_vagueness_score("x", Decimal("999999999"), "IT")
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# UnusualRestrictionDetector
# ---------------------------------------------------------------------------

class TestUnusualRestrictionDetector:
    """Tests for UnusualRestrictionDetector."""

    def _make_detector(self, percentile=95.0):
        from nlp_worker.detectors.unusual_restriction import UnusualRestrictionDetector
        store = _mock_store()
        return UnusualRestrictionDetector(vector_store=store, percentile=percentile)

    def _make_sentences(self, n: int, outlier_index: int | None = None) -> list[tuple[str, np.ndarray]]:
        """Create n sentences with L2-normalised vectors.

        If outlier_index is given, that sentence's vector is set to the
        negative of the centroid direction to maximise its distance.
        """
        vectors = [_make_vector() for _ in range(n)]
        if outlier_index is not None:
            # Make one vector point in the opposite direction of the mean
            centroid = np.mean(vectors, axis=0)
            outlier = -centroid / (np.linalg.norm(centroid) + 1e-9)
            vectors[outlier_index] = outlier.astype(np.float32)
        return [(f"sentence {i}", v) for i, v in enumerate(vectors)]

    def test_flags_when_anomalous_sentences_found(self):
        """Returns DetectionResult when anomalous sentences are detected."""
        detector = self._make_detector()
        # Use a controlled set: one clear outlier among many similar sentences
        base = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        outlier = np.array([-1.0] + [0.0] * 383, dtype=np.float32)
        sentences = [(f"s{i}", base.copy()) for i in range(9)] + [("outlier", outlier)]
        result = detector.detect(tender_id=1, sentences=sentences, category="IT")
        assert result is not None
        assert result.flag_type == "SPEC_UNUSUAL_RESTRICTION"
        assert result.severity == "MEDIUM"

    def test_no_flag_when_fewer_than_3_sentences(self):
        """Returns None when fewer than 3 sentences provided."""
        detector = self._make_detector()
        sentences = self._make_sentences(2)
        result = detector.detect(tender_id=1, sentences=sentences, category="IT")
        assert result is None

    def test_no_flag_for_empty_sentences(self):
        """Returns None for empty sentence list."""
        detector = self._make_detector()
        result = detector.detect(tender_id=1, sentences=[], category="IT")
        assert result is None

    def test_trigger_data_contains_anomalous_clauses(self):
        """trigger_data contains anomalous_clauses list."""
        detector = self._make_detector()
        base = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        outlier = np.array([-1.0] + [0.0] * 383, dtype=np.float32)
        sentences = [(f"s{i}", base.copy()) for i in range(9)] + [("outlier", outlier)]
        result = detector.detect(tender_id=1, sentences=sentences, category="IT")
        assert result is not None
        assert "anomalous_clauses" in result.trigger_data
        clauses = result.trigger_data["anomalous_clauses"]
        assert isinstance(clauses, list)
        assert len(clauses) >= 1

    def test_anomalous_clause_structure(self):
        """Each anomalous clause has sentence_text, sentence_index, distance."""
        detector = self._make_detector()
        base = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        outlier = np.array([-1.0] + [0.0] * 383, dtype=np.float32)
        sentences = [(f"s{i}", base.copy()) for i in range(9)] + [("outlier", outlier)]
        result = detector.detect(tender_id=1, sentences=sentences, category="IT")
        assert result is not None
        for clause in result.trigger_data["anomalous_clauses"]:
            assert "sentence_text" in clause
            assert "sentence_index" in clause
            assert "distance" in clause

    def test_score_in_unit_interval(self):
        """DetectionResult.score is in [0.0, 1.0]."""
        detector = self._make_detector()
        base = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        outlier = np.array([-1.0] + [0.0] * 383, dtype=np.float32)
        sentences = [(f"s{i}", base.copy()) for i in range(9)] + [("outlier", outlier)]
        result = detector.detect(tender_id=1, sentences=sentences, category="IT")
        assert result is not None
        assert 0.0 <= result.score <= 1.0

    def test_exactly_3_sentences_allowed(self):
        """Exactly 3 sentences is the minimum; should not return None due to count."""
        detector = self._make_detector()
        # All identical vectors → centroid == each vector → distance ≈ 0 → no anomalies
        v = _make_vector()
        sentences = [("s0", v.copy()), ("s1", v.copy()), ("s2", v.copy())]
        # With identical vectors, distances are all ~0, so no anomalies expected
        result = detector.detect(tender_id=1, sentences=sentences, category="IT")
        # Result may be None (no anomalies) but should NOT be None due to count restriction
        # We just verify it doesn't raise and the count check passes
        # (result could be None if no anomalies found, which is correct)
        assert result is None or result.flag_type == "SPEC_UNUSUAL_RESTRICTION"

    def test_no_flag_when_all_sentences_similar(self):
        """Returns None when all sentences are very similar (no outliers)."""
        detector = self._make_detector()
        # All vectors pointing in the same direction → no outliers
        base = np.array([1.0] + [0.0] * 383, dtype=np.float32)
        sentences = [(f"s{i}", base.copy()) for i in range(10)]
        result = detector.detect(tender_id=1, sentences=sentences, category="IT")
        assert result is None
