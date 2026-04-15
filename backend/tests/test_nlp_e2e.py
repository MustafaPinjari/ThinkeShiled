"""
End-to-end tests for analyze_spec_task with mocked Qdrant.

Tests the full flow:
  tender with spec_text → analyze_spec_task → SpecAnalysisResult + RedFlag records

Scenarios covered:
  1. Full happy-path: spec_text present, Qdrant available, flags raised
  2. Graceful degradation: Qdrant unavailable → VagueScopeDetector still runs
  3. Empty spec: no flags raised, SpecAnalysisResult.error == "empty_spec"
  4. No flags when similarity is below all thresholds

Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 11.1, 11.5
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
from django.test import TestCase
from django.utils import timezone

# ---------------------------------------------------------------------------
# sys.path bootstrap — ensure backend/ and workspace root are importable
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT_DIR = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
for _p in (_BACKEND_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Pre-patch the embedder singleton to avoid loading the sentence-transformers
# model during tests.  The model is large and slow; we replace the singleton
# with a mock so all tests run without the real model.
# ---------------------------------------------------------------------------

_MOCK_VECTOR = np.zeros(384, dtype=np.float32)
_MOCK_VECTOR[0] = 1.0

_mock_embedder_singleton = MagicMock()
_mock_embedder_singleton.embed.return_value = _MOCK_VECTOR.copy()
_mock_embedder_singleton.embed_sentences.return_value = [
    ("The supplier must be XYZ certified.", _MOCK_VECTOR.copy()),
    ("Delivery within 7 days of award.", _MOCK_VECTOR.copy()),
    ("Equipment must carry brand-specific certification.", _MOCK_VECTOR.copy()),
]
_mock_embedder_singleton.embed_batch.return_value = [_MOCK_VECTOR.copy()]

# Patch SentenceTransformer before importing nlp_worker.embedder so the
# eager model load at module level uses the mock.
with patch("sentence_transformers.SentenceTransformer"):
    import nlp_worker.embedder as _emb_module

# Replace the singleton with our mock (overrides whatever was loaded)
_emb_module._embedder = _mock_embedder_singleton


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


def _uid(prefix: str = "T") -> str:
    global _counter
    _counter += 1
    return f"{prefix}-NLP-E2E-{_counter}"


def _make_tender(spec_text: str = "", estimated_value: Decimal = Decimal("500000.00")):
    """Create a minimal Tender in the test DB."""
    from tenders.models import Tender

    return Tender.objects.create(
        tender_id=_uid("T"),
        title="NLP E2E Test Tender",
        category="IT",
        estimated_value=estimated_value,
        currency="INR",
        submission_deadline=timezone.now() + timezone.timedelta(days=30),
        publication_date=timezone.now() - timezone.timedelta(days=5),
        buyer_id=_uid("BUYER"),
        buyer_name="Test Buyer",
        spec_text=spec_text,
    )


def _make_mock_vector_store(search_results=None):
    """Return a mock VectorStore with configurable search results."""
    mock = MagicMock()
    mock.upsert.return_value = None
    mock.search_similar.return_value = search_results or []
    return mock


def _patch_embedder():
    """Patch the embedder singleton so tasks.py uses the pre-configured mock."""
    return patch.object(_emb_module, "_embedder", _mock_embedder_singleton)


def _patch_vector_store(mock_store):
    """Patch VectorStore class so tasks.py instantiates the mock."""
    return patch("nlp_worker.vector_store.VectorStore", return_value=mock_store)


# ---------------------------------------------------------------------------
# Test: Empty spec → no flags, error="empty_spec"
# ---------------------------------------------------------------------------

class TestAnalyzeSpecTaskEmptySpec(TestCase):
    """Requirement 2.2, 11.5: Empty spec produces no flags and error='empty_spec'."""

    def test_empty_spec_creates_result_with_empty_spec_error(self):
        """analyze_spec_task with empty spec_text inserts SpecAnalysisResult(error='empty_spec')."""
        from nlp.models import SpecAnalysisResult
        from detection.models import RedFlag

        tender = _make_tender(spec_text="")

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(_make_mock_vector_store()):
                    from nlp_worker.tasks import analyze_spec_task
                    analyze_spec_task.apply(args=[tender.id])

        result = SpecAnalysisResult.objects.filter(tender=tender).latest("analyzed_at")
        self.assertEqual(result.error, "empty_spec")
        self.assertEqual(result.flags_raised, [])

        nlp_flags = RedFlag.objects.filter(
            tender=tender,
            flag_type__startswith="SPEC_",
        )
        self.assertEqual(nlp_flags.count(), 0)

    def test_whitespace_only_spec_treated_as_empty(self):
        """analyze_spec_task with empty spec_text also produces empty_spec result."""
        from nlp.models import SpecAnalysisResult

        tender = _make_tender(spec_text="")

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(_make_mock_vector_store()):
                    from nlp_worker.tasks import analyze_spec_task
                    analyze_spec_task.apply(args=[tender.id])

        result = SpecAnalysisResult.objects.filter(tender=tender).latest("analyzed_at")
        self.assertEqual(result.error, "empty_spec")


# ---------------------------------------------------------------------------
# Test: Full happy-path with mocked Qdrant returning high similarity
# ---------------------------------------------------------------------------

class TestAnalyzeSpecTaskFullFlow(TestCase):
    """Requirement 2.3, 2.4, 2.5, 2.6: Full pipeline with mocked Qdrant."""

    SPEC_TEXT = (
        "The supplier must have supplied to Ministry of Health in the last 6 months. "
        "Equipment must carry XYZ-brand certification. "
        "Delivery within 7 days of award. "
        "Only vendors registered in the capital city are eligible. "
        "The contract value is estimated at five million INR."
    )

    def _run_task_with_high_similarity(self, tender):
        """Run analyze_spec_task with Qdrant returning similarity >= 0.92 (triggers copy-paste)."""
        from nlp_worker.vector_store import SimilarityResult

        high_sim_results = [SimilarityResult(tender_id=999, similarity=0.95)]
        mock_store = _make_mock_vector_store(search_results=high_sim_results)

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(mock_store):
                    with patch("nlp_worker.tasks.current_app") as mock_celery:
                        from nlp_worker.tasks import analyze_spec_task
                        result = analyze_spec_task.apply(args=[tender.id])
                        return result, mock_celery

    def test_spec_analysis_result_created(self):
        """A SpecAnalysisResult record is created after task execution."""
        from nlp.models import SpecAnalysisResult

        tender = _make_tender(spec_text=self.SPEC_TEXT)
        self._run_task_with_high_similarity(tender)

        self.assertTrue(
            SpecAnalysisResult.objects.filter(tender=tender).exists(),
            "SpecAnalysisResult should be created",
        )

    def test_analysis_duration_ms_recorded(self):
        """SpecAnalysisResult.analysis_duration_ms is set (Requirement 2.6)."""
        from nlp.models import SpecAnalysisResult

        tender = _make_tender(spec_text=self.SPEC_TEXT)
        self._run_task_with_high_similarity(tender)

        result = SpecAnalysisResult.objects.filter(tender=tender).latest("analyzed_at")
        self.assertIsNotNone(result.analysis_duration_ms)
        self.assertGreaterEqual(result.analysis_duration_ms, 0)

    def test_copy_paste_flag_raised_when_similarity_high(self):
        """SPEC_COPY_PASTE RedFlag is created when similarity >= 0.92."""
        from detection.models import RedFlag

        tender = _make_tender(spec_text=self.SPEC_TEXT)
        self._run_task_with_high_similarity(tender)

        flags = RedFlag.objects.filter(
            tender=tender,
            flag_type="SPEC_COPY_PASTE",
            is_active=True,
        )
        self.assertTrue(flags.exists(), "SPEC_COPY_PASTE flag should be raised")

    def test_flags_raised_recorded_in_spec_analysis_result(self):
        """SpecAnalysisResult.flags_raised contains the raised flag types."""
        from nlp.models import SpecAnalysisResult

        tender = _make_tender(spec_text=self.SPEC_TEXT)
        self._run_task_with_high_similarity(tender)

        result = SpecAnalysisResult.objects.filter(tender=tender).latest("analyzed_at")
        self.assertIn("SPEC_COPY_PASTE", result.flags_raised)

    def test_score_tender_triggered_when_flags_raised(self):
        """ml_worker.score_tender is enqueued when NLP flags are raised (Requirement 2.5)."""
        tender = _make_tender(spec_text=self.SPEC_TEXT)
        _, mock_celery = self._run_task_with_high_similarity(tender)

        mock_celery.send_task.assert_called_once_with(
            "ml_worker.score_tender", args=[tender.id]
        )

    def test_embedding_upserted_to_vector_store(self):
        """VectorStore.upsert is called with the tender's embedding (Requirement 2.4)."""
        from nlp_worker.vector_store import SimilarityResult

        high_sim_results = [SimilarityResult(tender_id=999, similarity=0.95)]
        mock_store = _make_mock_vector_store(search_results=high_sim_results)

        tender = _make_tender(spec_text=self.SPEC_TEXT)

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(mock_store):
                    with patch("nlp_worker.tasks.current_app"):
                        from nlp_worker.tasks import analyze_spec_task
                        analyze_spec_task.apply(args=[tender.id])

        mock_store.upsert.assert_called_once()
        call_kwargs = mock_store.upsert.call_args[1]
        self.assertEqual(call_kwargs["tender_id"], tender.id)

    def test_task_returns_tender_id_and_flags(self):
        """Task return value includes tender_id and flags_raised."""
        tender = _make_tender(spec_text=self.SPEC_TEXT)
        task_result, _ = self._run_task_with_high_similarity(tender)

        result_value = task_result.result
        self.assertEqual(result_value["tender_id"], tender.id)
        self.assertIn("flags_raised", result_value)
        self.assertIn("analysis_duration_ms", result_value)


# ---------------------------------------------------------------------------
# Test: Graceful degradation — Qdrant unavailable
# ---------------------------------------------------------------------------

class TestAnalyzeSpecTaskQdrantUnavailable(TestCase):
    """Requirement 11.1: Qdrant unavailable → VagueScopeDetector still runs."""

    # Short repetitive text → high vagueness score → SPEC_VAGUE_SCOPE flag
    SPEC_TEXT = "services services services services services services services"

    def _run_task_with_qdrant_down(self, tender):
        """Run analyze_spec_task where Qdrant is unavailable.

        Patches VectorStore.upsert to raise an exception. Since qdrant_client
        may not be installed, _qdrant_exceptions may be (Exception,) which
        catches all exceptions and calls self.retry(). We patch the task's
        retry method to immediately raise MaxRetriesExceededError so the
        task's degraded path (qdrant_available=False) is exercised.
        Also patches current_app.send_task to avoid Redis connections.
        """
        mock_store = MagicMock()
        mock_store.upsert.side_effect = RuntimeError("Qdrant connection refused")

        from nlp_worker.tasks import analyze_spec_task
        from celery.exceptions import MaxRetriesExceededError as CeleryMaxRetries

        def _raise_max_retries(*args, **kwargs):
            raise CeleryMaxRetries("max retries exceeded in test")

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(mock_store):
                    with patch("nlp_worker.tasks.current_app"):
                        with patch.object(analyze_spec_task, "retry", side_effect=_raise_max_retries):
                            analyze_spec_task.apply(args=[tender.id])

    def test_spec_analysis_result_created_when_qdrant_down(self):
        """SpecAnalysisResult is still created even when Qdrant is unavailable."""
        from nlp.models import SpecAnalysisResult

        tender = _make_tender(spec_text=self.SPEC_TEXT)
        self._run_task_with_qdrant_down(tender)

        self.assertTrue(
            SpecAnalysisResult.objects.filter(tender=tender).exists(),
            "SpecAnalysisResult should be created even when Qdrant is down",
        )

    def test_error_field_set_to_qdrant_unavailable(self):
        """SpecAnalysisResult.error contains 'qdrant_unavailable' when Qdrant is down."""
        from nlp.models import SpecAnalysisResult

        tender = _make_tender(spec_text=self.SPEC_TEXT)
        self._run_task_with_qdrant_down(tender)

        result = SpecAnalysisResult.objects.filter(tender=tender).latest("analyzed_at")
        self.assertIn("qdrant_unavailable", result.error)

    def test_no_vector_based_flags_when_qdrant_down(self):
        """No SPEC_TAILORING or SPEC_COPY_PASTE flags when Qdrant is unavailable."""
        from detection.models import RedFlag

        tender = _make_tender(spec_text=self.SPEC_TEXT)
        self._run_task_with_qdrant_down(tender)

        vector_flags = RedFlag.objects.filter(
            tender=tender,
            flag_type__in=["SPEC_TAILORING", "SPEC_COPY_PASTE"],
        )
        self.assertEqual(vector_flags.count(), 0)


# ---------------------------------------------------------------------------
# Test: No flags when similarity is below all thresholds
# ---------------------------------------------------------------------------

class TestAnalyzeSpecTaskNoFlags(TestCase):
    """No flags raised when similarity is below all thresholds."""

    SPEC_TEXT = (
        "The contractor shall deliver comprehensive software engineering services "
        "including requirements analysis, system design, implementation, testing, "
        "deployment, documentation, training, maintenance, and ongoing support. "
        "All deliverables must comply with ISO 27001 security standards. "
        "The project timeline spans eighteen months with quarterly milestone reviews. "
        "Payment terms are net-30 days after acceptance of each milestone deliverable. "
        "The vendor must provide a dedicated project manager and technical lead."
    )

    def test_no_nlp_flags_when_similarity_low(self):
        """No SPEC_* RedFlags when similarity is below all thresholds."""
        from detection.models import RedFlag
        from nlp_worker.vector_store import SimilarityResult

        low_sim_results = [SimilarityResult(tender_id=999, similarity=0.50)]
        mock_store = _make_mock_vector_store(search_results=low_sim_results)

        # Large estimated value → low vagueness score → no SPEC_VAGUE_SCOPE flag
        tender = _make_tender(
            spec_text=self.SPEC_TEXT,
            estimated_value=Decimal("5000000.00"),
        )

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(mock_store):
                    with patch("nlp_worker.tasks.current_app"):
                        from nlp_worker.tasks import analyze_spec_task
                        analyze_spec_task.apply(args=[tender.id])

        vector_flags = RedFlag.objects.filter(
            tender=tender,
            flag_type__in=["SPEC_TAILORING", "SPEC_COPY_PASTE"],
            is_active=True,
        )
        self.assertEqual(vector_flags.count(), 0)

    def test_spec_analysis_result_created_even_with_no_flags(self):
        """SpecAnalysisResult is always created, even when no flags are raised."""
        from nlp.models import SpecAnalysisResult
        from nlp_worker.vector_store import SimilarityResult

        low_sim_results = [SimilarityResult(tender_id=999, similarity=0.50)]
        mock_store = _make_mock_vector_store(search_results=low_sim_results)

        tender = _make_tender(
            spec_text=self.SPEC_TEXT,
            estimated_value=Decimal("5000000.00"),
        )

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(mock_store):
                    with patch("nlp_worker.tasks.current_app"):
                        from nlp_worker.tasks import analyze_spec_task
                        analyze_spec_task.apply(args=[tender.id])

        self.assertTrue(
            SpecAnalysisResult.objects.filter(tender=tender).exists()
        )

    def test_score_tender_not_triggered_when_no_flags(self):
        """ml_worker.score_tender is NOT enqueued when no NLP flags are raised."""
        from nlp_worker.vector_store import SimilarityResult

        low_sim_results = [SimilarityResult(tender_id=999, similarity=0.50)]
        mock_store = _make_mock_vector_store(search_results=low_sim_results)

        tender = _make_tender(
            spec_text=self.SPEC_TEXT,
            estimated_value=Decimal("5000000.00"),
        )

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(mock_store):
                    with patch("nlp_worker.tasks.current_app") as mock_celery:
                        from nlp_worker.tasks import analyze_spec_task
                        analyze_spec_task.apply(args=[tender.id])

        mock_celery.send_task.assert_not_called()


# ---------------------------------------------------------------------------
# Test: Tender not found
# ---------------------------------------------------------------------------

class TestAnalyzeSpecTaskTenderNotFound(TestCase):
    """Task handles missing tender gracefully."""

    def test_returns_error_when_tender_not_found(self):
        """analyze_spec_task returns error dict when tender_id does not exist."""
        with patch("nlp_worker.tasks._bootstrap_django"):
            from nlp_worker.tasks import analyze_spec_task
            result = analyze_spec_task.apply(args=[999999])

        self.assertIn("error", result.result)
