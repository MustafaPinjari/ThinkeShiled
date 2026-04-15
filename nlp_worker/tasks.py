"""
Celery tasks for the TenderShield NLP worker.

Tasks
-----
analyze_spec_task(tender_id)
    Embed the tender's spec_text, run all four NLP detectors, write RedFlag
    records and SpecClauseHighlight records, persist a SpecAnalysisResult,
    and trigger FraudRiskScore recomputation if any flags were raised.

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 1.4, 11.1, 11.2, 11.3, 11.4, 11.5
"""

from __future__ import annotations

import logging
import os
import time

import django

# Bootstrap Django so ORM is available when the worker imports this module.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")


def _bootstrap_django() -> None:
    """Bootstrap Django ORM when running inside the nlp_worker process."""
    try:
        from django.conf import settings as _s

        if not _s.configured:
            django.setup()
        elif not _s.INSTALLED_APPS:
            pass
    except Exception:
        pass  # Running outside Django context (e.g., pure unit tests)


_bootstrap_django()

from celery import current_app, shared_task
from django.utils import timezone as dj_timezone

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers — Django ORM imports (deferred to avoid circular imports)
# ---------------------------------------------------------------------------

def _get_models():
    """Return Django model classes (imported lazily)."""
    from audit.models import AuditLog, EventType
    from nlp.models import SpecAnalysisResult
    from tenders.models import Tender

    return {
        "AuditLog": AuditLog,
        "EventType": EventType,
        "SpecAnalysisResult": SpecAnalysisResult,
        "Tender": Tender,
    }


# ---------------------------------------------------------------------------
# Main NLP analysis Celery task
# ---------------------------------------------------------------------------

@shared_task(
    name="nlp_worker.analyze_spec_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def analyze_spec_task(self, tender_id: int) -> dict:
    """Analyse the specification text of a tender using the NLP pipeline.

    Algorithm
    ---------
    1. Fetch Tender by tender_id; if spec_text is empty → insert
       SpecAnalysisResult(error="empty_spec") and return.
    2. Detect language with langdetect; update Tender.spec_language.
    3. Embed full spec and sentences via SpecEmbedder.
    4. Upsert embedding to VectorStore; on QdrantException → set
       error="qdrant_unavailable", skip vector detectors, still run
       VagueScopeDetector.
    5. Run all four detectors; catch per-detector exceptions individually
       (log + continue).
    6. Call NLPFlagWriter.write_flags().
    7. Insert SpecAnalysisResult with all scores, flags_raised,
       analysis_duration_ms.
    8. If any flags raised: trigger ml_worker.score_tender.
    9. On Qdrant retry exhaustion: write AuditLog entry.
    """
    m = _get_models()
    Tender = m["Tender"]
    SpecAnalysisResult = m["SpecAnalysisResult"]
    AuditLog = m["AuditLog"]
    EventType = m["EventType"]

    start_time = time.monotonic()

    # ------------------------------------------------------------------
    # 1. Fetch tender
    # ------------------------------------------------------------------
    try:
        tender = Tender.objects.get(pk=tender_id)
    except Tender.DoesNotExist:
        logger.error("analyze_spec_task: Tender %s not found.", tender_id)
        return {"error": f"Tender {tender_id} not found"}

    # ------------------------------------------------------------------
    # 2. Graceful degradation: empty spec → no analysis, no false positives
    #    (Requirements 2.2, 11.5)
    # ------------------------------------------------------------------
    if not tender.spec_text:
        logger.info(
            "analyze_spec_task: Tender %s has empty spec_text; inserting empty_spec result.",
            tender_id,
        )
        SpecAnalysisResult.objects.create(
            tender=tender,
            error="empty_spec",
            analyzed_at=dj_timezone.now(),
        )
        return {"tender_id": tender_id, "status": "empty_spec"}

    # ------------------------------------------------------------------
    # 3. Detect language (Requirement 1.4)
    # ------------------------------------------------------------------
    detected_language = ""
    try:
        from langdetect import detect as langdetect_detect
        from langdetect.lang_detect_exception import LangDetectException

        detected_language = langdetect_detect(tender.spec_text)
    except Exception:
        logger.warning(
            "analyze_spec_task: Language detection failed for tender_id=%s; "
            "defaulting to empty string.",
            tender_id,
        )
        detected_language = ""

    # Persist detected language on the Tender record
    try:
        Tender.objects.filter(pk=tender_id).update(spec_language=detected_language)
        tender.spec_language = detected_language
    except Exception:
        logger.warning(
            "analyze_spec_task: Failed to update spec_language for tender_id=%s.",
            tender_id,
        )

    # ------------------------------------------------------------------
    # 4. Embed full spec and sentences (Requirement 3.x)
    # ------------------------------------------------------------------
    from nlp_worker.embedder import _get_embedder

    embedder = _get_embedder()
    vector = embedder.embed(tender.spec_text)
    sentences = embedder.embed_sentences(tender.spec_text)

    # ------------------------------------------------------------------
    # 5. Upsert embedding to VectorStore (Requirement 2.4, 11.1)
    # ------------------------------------------------------------------
    from nlp_worker.vector_store import VectorStore

    qdrant_available = True
    qdrant_error_msg = ""

    try:
        from qdrant_client.http.exceptions import (
            ResponseHandlingException,
            UnexpectedResponse,
        )
        _qdrant_exceptions = (ResponseHandlingException, UnexpectedResponse)
    except ImportError:
        _qdrant_exceptions = (Exception,)

    vector_store = VectorStore()

    try:
        vector_store.upsert(
            tender_id=tender_id,
            vector=vector,
            payload={
                "category": tender.category,
                "is_fraud_corpus": False,
                "confirmed_fraud": False,
                "ingested_at": dj_timezone.now().isoformat(),
            },
        )
    except _qdrant_exceptions as exc:
        qdrant_error_msg = str(exc)
        logger.error(
            "analyze_spec_task: Qdrant upsert failed for tender_id=%s: %s. "
            "Will retry with exponential backoff.",
            tender_id,
            exc,
        )
        # Retry with exponential backoff (Requirement 11.3)
        countdown = 60 * (2 ** self.request.retries)
        try:
            raise self.retry(exc=exc, countdown=countdown)
        except self.MaxRetriesExceededError:
            # All retries exhausted — write AuditLog and continue degraded
            # (Requirement 11.4)
            logger.error(
                "analyze_spec_task: All retries exhausted for tender_id=%s. "
                "Writing AuditLog entry.",
                tender_id,
            )
            try:
                AuditLog.objects.create(
                    event_type=EventType.SHAP_FAILED,  # closest available event type
                    user=None,
                    affected_entity_type="Tender",
                    affected_entity_id=str(tender_id),
                    data_snapshot={
                        "task": "nlp_worker.analyze_spec_task",
                        "tender_id": tender_id,
                        "failure_reason": f"qdrant_unavailable: {qdrant_error_msg}",
                    },
                )
            except Exception:
                logger.exception(
                    "analyze_spec_task: Failed to write AuditLog for tender_id=%s.",
                    tender_id,
                )
            qdrant_available = False
            qdrant_error_msg = f"qdrant_unavailable after max retries: {qdrant_error_msg}"
    except Exception as exc:
        logger.error(
            "analyze_spec_task: Unexpected error during Qdrant upsert for "
            "tender_id=%s: %s. Continuing without vector store.",
            tender_id,
            exc,
        )
        qdrant_available = False
        qdrant_error_msg = str(exc)

    # ------------------------------------------------------------------
    # 6. Run detectors (Requirement 2.3, 11.1, 11.2)
    # ------------------------------------------------------------------
    from nlp_worker.detectors.tailoring import TailoringDetector
    from nlp_worker.detectors.copy_paste import CopyPasteDetector
    from nlp_worker.detectors.vague_scope import VagueScopeDetector
    from nlp_worker.detectors.unusual_restriction import UnusualRestrictionDetector

    results = []
    error_messages = []

    # Vector-based detectors — only run if Qdrant is available (Requirement 11.1)
    if qdrant_available:
        # Tailoring detector
        try:
            tailoring_detector = TailoringDetector(vector_store=vector_store)
            result = tailoring_detector.detect(
                tender_id=tender_id,
                vector=vector,
                category=tender.category,
            )
            results.append(result)
        except Exception as exc:
            logger.exception(
                "analyze_spec_task: TailoringDetector failed for tender_id=%s: %s",
                tender_id,
                exc,
            )
            error_messages.append(f"tailoring_detector: {exc}")
            results.append(None)

        # Copy-paste detector
        try:
            copy_paste_detector = CopyPasteDetector(vector_store=vector_store)
            result = copy_paste_detector.detect(
                tender_id=tender_id,
                vector=vector,
            )
            results.append(result)
        except Exception as exc:
            logger.exception(
                "analyze_spec_task: CopyPasteDetector failed for tender_id=%s: %s",
                tender_id,
                exc,
            )
            error_messages.append(f"copy_paste_detector: {exc}")
            results.append(None)
    else:
        # Skip vector-based detectors when Qdrant is unavailable
        logger.warning(
            "analyze_spec_task: Skipping vector-based detectors for tender_id=%s "
            "(Qdrant unavailable).",
            tender_id,
        )
        results.append(None)  # tailoring placeholder
        results.append(None)  # copy_paste placeholder

    # Vague scope detector — always runs (Requirement 11.1)
    try:
        vague_scope_detector = VagueScopeDetector()
        result = vague_scope_detector.detect(
            tender_id=tender_id,
            spec_text=tender.spec_text,
            estimated_value=tender.estimated_value,
            category=tender.category,
        )
        results.append(result)
    except Exception as exc:
        logger.exception(
            "analyze_spec_task: VagueScopeDetector failed for tender_id=%s: %s",
            tender_id,
            exc,
        )
        error_messages.append(f"vague_scope_detector: {exc}")
        results.append(None)

    # Unusual restriction detector — only run if Qdrant is available
    if qdrant_available:
        try:
            restriction_detector = UnusualRestrictionDetector(vector_store=vector_store)
            result = restriction_detector.detect(
                tender_id=tender_id,
                sentences=sentences,
                category=tender.category,
            )
            results.append(result)
        except Exception as exc:
            logger.exception(
                "analyze_spec_task: UnusualRestrictionDetector failed for tender_id=%s: %s",
                tender_id,
                exc,
            )
            error_messages.append(f"unusual_restriction_detector: {exc}")
            results.append(None)
    else:
        results.append(None)  # unusual_restriction placeholder

    # ------------------------------------------------------------------
    # 7. Write flags (Requirement 2.3, 8.1, 9.4)
    # ------------------------------------------------------------------
    from nlp_worker.flag_writer import NLPFlagWriter

    non_null_results = [r for r in results if r is not None]

    # Create a preliminary SpecAnalysisResult so flag_writer can update it
    duration_ms = int((time.monotonic() - start_time) * 1000)

    error_field = ""
    if not qdrant_available:
        error_field = "qdrant_unavailable"
    if error_messages:
        combined_errors = "; ".join(error_messages)
        error_field = (error_field + "; " + combined_errors).lstrip("; ") if error_field else combined_errors

    spec_result = SpecAnalysisResult.objects.create(
        tender=tender,
        spec_language=detected_language,
        analyzed_at=dj_timezone.now(),
        analysis_duration_ms=duration_ms,
        error=error_field,
        flags_raised=[],
    )

    flag_writer = NLPFlagWriter()
    created_flags = flag_writer.write_flags(
        tender_id=tender_id,
        results=non_null_results,
        spec_text=tender.spec_text,
        spec_analysis_result=spec_result,
    )

    # ------------------------------------------------------------------
    # 8. Trigger FraudRiskScore recomputation if any flags raised
    #    (Requirement 2.5)
    # ------------------------------------------------------------------
    flags_raised = [f.flag_type for f in created_flags]

    if flags_raised:
        logger.info(
            "analyze_spec_task: %d NLP flag(s) raised for tender_id=%s; "
            "triggering ml_worker.score_tender.",
            len(flags_raised),
            tender_id,
        )
        current_app.send_task("ml_worker.score_tender", args=[tender_id])

    logger.info(
        "analyze_spec_task: Completed for tender_id=%s in %dms. "
        "flags_raised=%s qdrant_available=%s",
        tender_id,
        duration_ms,
        flags_raised,
        qdrant_available,
    )

    return {
        "tender_id": tender_id,
        "flags_raised": flags_raised,
        "analysis_duration_ms": duration_ms,
        "qdrant_available": qdrant_available,
        "spec_language": detected_language,
    }
