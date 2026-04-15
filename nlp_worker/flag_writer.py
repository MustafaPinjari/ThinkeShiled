"""
NLPFlagWriter — translates DetectionResult objects into RedFlag and
SpecClauseHighlight database records.

Requirements: 4.3, 5.3, 6.5, 7.4, 8.1, 9.4
"""

from __future__ import annotations

import logging
import os

import django

logger = logging.getLogger(__name__)


def _bootstrap_django() -> None:
    """Bootstrap Django ORM when running inside the nlp_worker process.

    Called lazily (inside write_flags) rather than at module import time so
    that importing this module in unit-test contexts does not trigger a full
    Django setup and interfere with pytest-django fixtures.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.conf import settings as _s

        if not _s.configured:
            django.setup()
    except Exception:
        pass  # Running outside Django context (e.g., pure unit tests)

# Flag type → SpecAnalysisResult field names
_TAILORING_FLAG = "SPEC_TAILORING"
_COPY_PASTE_FLAG = "SPEC_COPY_PASTE"
_VAGUE_SCOPE_FLAG = "SPEC_VAGUE_SCOPE"
_UNUSUAL_RESTRICTION_FLAG = "SPEC_UNUSUAL_RESTRICTION"


def _get_models():
    """Lazily import Django models to avoid circular imports at module load."""
    from detection.models import RedFlag
    from nlp.models import SpecAnalysisResult, SpecClauseHighlight

    return RedFlag, SpecAnalysisResult, SpecClauseHighlight


class NLPFlagWriter:
    """Write NLP detection results to the database.

    Responsibilities:
    - Clear previously active NLP RedFlag records for the tender.
    - Create one RedFlag per non-None DetectionResult.
    - Create SpecClauseHighlight records via ClauseHighlighter.
    - Optionally update a SpecAnalysisResult instance with per-detector scores.
    """

    def write_flags(
        self,
        tender_id: int,
        results: list,
        spec_text: str = "",
        spec_analysis_result=None,
    ) -> list:
        """Write NLP flags for a tender.

        Args:
            tender_id: Primary key of the Tender being analysed.
            results: List of DetectionResult objects (non-None only; callers
                should filter out None values before calling).
            spec_text: Full specification text, forwarded to ClauseHighlighter.
            spec_analysis_result: Optional SpecAnalysisResult instance.  When
                provided, its score fields are updated and saved.

        Returns:
            List of created RedFlag instances.
        """
        _bootstrap_django()
        RedFlag, SpecAnalysisResult, SpecClauseHighlight = _get_models()

        # ------------------------------------------------------------------
        # 1. Clear previously active NLP RedFlag records (Requirement 9.4)
        # ------------------------------------------------------------------
        cleared = RedFlag.objects.filter(
            tender_id=tender_id,
            flag_type__startswith="SPEC_",
            is_active=True,
        )
        for flag in cleared:
            flag.clear()

        # ------------------------------------------------------------------
        # 2. Create one RedFlag per DetectionResult (Requirement 8.1)
        # ------------------------------------------------------------------
        from nlp_worker.highlighter import ClauseHighlighter

        highlighter = ClauseHighlighter()
        created_flags: list = []

        for result in results:
            if result is None:
                continue

            try:
                red_flag = RedFlag.objects.create(
                    tender_id=tender_id,
                    flag_type=result.flag_type,
                    severity=result.severity,
                    trigger_data=result.trigger_data,
                    rule_version="nlp-1.0",
                )
            except Exception:
                logger.exception(
                    "NLPFlagWriter: failed to create RedFlag for tender_id=%s flag_type=%s",
                    tender_id,
                    result.flag_type,
                )
                continue

            created_flags.append(red_flag)

            # ------------------------------------------------------------------
            # 3. Create SpecClauseHighlight records (Requirements 4.4, 7.3, 8.1)
            # ------------------------------------------------------------------
            try:
                highlights = highlighter.highlight(
                    spec_text=spec_text,
                    flag_type=result.flag_type,
                    trigger_data=result.trigger_data,
                )
                for h in highlights:
                    SpecClauseHighlight.objects.create(
                        tender_id=tender_id,
                        red_flag=red_flag,
                        sentence_text=h.sentence_text,
                        sentence_index=h.sentence_index,
                        relevance_score=h.relevance_score,
                        reason=h.reason[:500],
                    )
            except Exception:
                logger.exception(
                    "NLPFlagWriter: failed to create SpecClauseHighlight for "
                    "tender_id=%s flag_type=%s",
                    tender_id,
                    result.flag_type,
                )

        # ------------------------------------------------------------------
        # 4. Update SpecAnalysisResult if provided (Requirements 4.3, 5.3, 6.5, 7.4)
        # ------------------------------------------------------------------
        if spec_analysis_result is not None:
            self._update_analysis_result(spec_analysis_result, results, created_flags)

        return created_flags

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _update_analysis_result(
        self,
        spec_analysis_result,
        results: list,
        created_flags: list,
    ) -> None:
        """Populate score fields on a SpecAnalysisResult and save it."""
        # Build a lookup: flag_type → DetectionResult
        result_by_type: dict = {}
        for r in results:
            if r is not None:
                result_by_type[r.flag_type] = r

        update_fields: list[str] = []

        # Tailoring (Requirement 4.3)
        tailoring = result_by_type.get(_TAILORING_FLAG)
        if tailoring is not None:
            spec_analysis_result.tailoring_similarity = tailoring.score
            spec_analysis_result.tailoring_matched_tender_id = (
                tailoring.trigger_data.get("matched_tender_id")
            )
            update_fields += ["tailoring_similarity", "tailoring_matched_tender_id"]

        # Copy-paste (Requirement 5.3)
        copy_paste = result_by_type.get(_COPY_PASTE_FLAG)
        if copy_paste is not None:
            spec_analysis_result.copy_paste_similarity = copy_paste.score
            spec_analysis_result.copy_paste_matched_tender_id = (
                copy_paste.trigger_data.get("matched_tender_id")
            )
            update_fields += ["copy_paste_similarity", "copy_paste_matched_tender_id"]

        # Vague scope (Requirement 6.5)
        vague = result_by_type.get(_VAGUE_SCOPE_FLAG)
        if vague is not None:
            spec_analysis_result.vagueness_score = vague.score
            update_fields.append("vagueness_score")

        # Unusual restriction (Requirement 7.4)
        unusual = result_by_type.get(_UNUSUAL_RESTRICTION_FLAG)
        if unusual is not None:
            spec_analysis_result.unusual_restriction_score = unusual.score
            update_fields.append("unusual_restriction_score")

        # flags_raised — list of flag_type strings from created flags
        spec_analysis_result.flags_raised = [f.flag_type for f in created_flags]
        update_fields.append("flags_raised")

        if update_fields:
            try:
                spec_analysis_result.save(update_fields=update_fields)
            except Exception:
                logger.exception(
                    "NLPFlagWriter: failed to update SpecAnalysisResult pk=%s",
                    getattr(spec_analysis_result, "pk", None),
                )
