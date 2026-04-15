"""
Unit tests for NLPFlagWriter.

All Django ORM calls are mocked so no real database is needed.

Requirements: 4.3, 5.3, 6.5, 7.4, 8.1, 9.4
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from nlp_worker.detectors import DetectionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    flag_type: str = "SPEC_TAILORING",
    severity: str = "HIGH",
    score: float = 0.90,
    trigger_data: dict | None = None,
) -> DetectionResult:
    return DetectionResult(
        flag_type=flag_type,
        severity=severity,
        score=score,
        trigger_data=trigger_data or {},
    )


def _make_red_flag(flag_type: str = "SPEC_TAILORING", pk: int = 1) -> MagicMock:
    flag = MagicMock()
    flag.pk = pk
    flag.id = pk
    flag.flag_type = flag_type
    return flag


def _make_spec_analysis_result() -> MagicMock:
    sar = MagicMock()
    sar.pk = 99
    sar.tailoring_similarity = None
    sar.tailoring_matched_tender_id = None
    sar.copy_paste_similarity = None
    sar.copy_paste_matched_tender_id = None
    sar.vagueness_score = None
    sar.unusual_restriction_score = None
    sar.flags_raised = []
    return sar


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _no_django_bootstrap():
    """Prevent _bootstrap_django from running during tests."""
    with patch("nlp_worker.flag_writer._bootstrap_django"):
        yield


@pytest.fixture()
def writer():
    from nlp_worker.flag_writer import NLPFlagWriter
    return NLPFlagWriter()


@pytest.fixture()
def mock_models():
    """Patch _get_models to return mock Django model classes."""
    RedFlag = MagicMock()
    SpecAnalysisResult = MagicMock()
    SpecClauseHighlight = MagicMock()

    with patch(
        "nlp_worker.flag_writer._get_models",
        return_value=(RedFlag, SpecAnalysisResult, SpecClauseHighlight),
    ):
        yield RedFlag, SpecAnalysisResult, SpecClauseHighlight


@pytest.fixture()
def mock_highlighter():
    """Patch ClauseHighlighter to return empty highlights by default."""
    with patch("nlp_worker.highlighter.ClauseHighlighter") as MockHighlighter:
        instance = MockHighlighter.return_value
        instance.highlight.return_value = []
        yield instance


# ---------------------------------------------------------------------------
# Tests: clearing old flags (Requirement 9.4)
# ---------------------------------------------------------------------------

class TestClearOldFlags:
    def test_clears_active_spec_flags_before_writing(self, writer, mock_models, mock_highlighter):
        """Previously active SPEC_* flags are cleared before new ones are written."""
        RedFlag, _, _ = mock_models

        old_flag1 = MagicMock()
        old_flag2 = MagicMock()
        RedFlag.objects.filter.return_value = [old_flag1, old_flag2]
        RedFlag.objects.create.return_value = _make_red_flag()

        writer.write_flags(tender_id=1, results=[_make_result()])

        RedFlag.objects.filter.assert_called_once_with(
            tender_id=1,
            flag_type__startswith="SPEC_",
            is_active=True,
        )
        old_flag1.clear.assert_called_once()
        old_flag2.clear.assert_called_once()

    def test_clears_flags_even_when_results_empty(self, writer, mock_models, mock_highlighter):
        """Old flags are cleared even when results list is empty."""
        RedFlag, _, _ = mock_models
        old_flag = MagicMock()
        RedFlag.objects.filter.return_value = [old_flag]

        writer.write_flags(tender_id=5, results=[])

        old_flag.clear.assert_called_once()

    def test_no_flags_created_when_results_empty(self, writer, mock_models, mock_highlighter):
        """No RedFlag records are created when results is empty."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []

        result = writer.write_flags(tender_id=1, results=[])

        RedFlag.objects.create.assert_not_called()
        assert result == []


# ---------------------------------------------------------------------------
# Tests: creating RedFlag records (Requirement 8.1)
# ---------------------------------------------------------------------------

class TestCreateRedFlags:
    def test_creates_one_flag_per_result(self, writer, mock_models, mock_highlighter):
        """Exactly one RedFlag is created per DetectionResult."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.side_effect = [
            _make_red_flag("SPEC_TAILORING", pk=1),
            _make_red_flag("SPEC_COPY_PASTE", pk=2),
        ]

        results = [
            _make_result("SPEC_TAILORING"),
            _make_result("SPEC_COPY_PASTE", severity="HIGH", score=0.95),
        ]
        flags = writer.write_flags(tender_id=1, results=results)

        assert RedFlag.objects.create.call_count == 2
        assert len(flags) == 2

    def test_flag_created_with_correct_fields(self, writer, mock_models, mock_highlighter):
        """RedFlag is created with correct flag_type, severity, trigger_data, rule_version."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        created_flag = _make_red_flag("SPEC_VAGUE_SCOPE", pk=3)
        RedFlag.objects.create.return_value = created_flag

        trigger = {"vagueness_score": 0.85, "word_count": 5}
        result = _make_result("SPEC_VAGUE_SCOPE", severity="MEDIUM", score=0.85, trigger_data=trigger)
        writer.write_flags(tender_id=7, results=[result])

        RedFlag.objects.create.assert_called_once_with(
            tender_id=7,
            flag_type="SPEC_VAGUE_SCOPE",
            severity="MEDIUM",
            trigger_data=trigger,
            rule_version="nlp-1.0",
        )

    def test_returns_created_flags(self, writer, mock_models, mock_highlighter):
        """write_flags returns the list of created RedFlag objects."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        flag = _make_red_flag("SPEC_TAILORING", pk=10)
        RedFlag.objects.create.return_value = flag

        returned = writer.write_flags(tender_id=1, results=[_make_result()])

        assert returned == [flag]

    def test_rule_version_is_nlp_1_0(self, writer, mock_models, mock_highlighter):
        """rule_version is always 'nlp-1.0'."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.return_value = _make_red_flag()

        writer.write_flags(tender_id=1, results=[_make_result()])

        _, kwargs = RedFlag.objects.create.call_args
        assert kwargs["rule_version"] == "nlp-1.0"


# ---------------------------------------------------------------------------
# Tests: SpecClauseHighlight creation (Requirements 4.4, 7.3, 8.1)
# ---------------------------------------------------------------------------

class TestCreateClauseHighlights:
    def test_highlight_called_for_each_flag(self, writer, mock_models, mock_highlighter):
        """ClauseHighlighter.highlight is called once per created flag."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.side_effect = [
            _make_red_flag("SPEC_TAILORING", pk=1),
            _make_red_flag("SPEC_VAGUE_SCOPE", pk=2),
        ]

        results = [_make_result("SPEC_TAILORING"), _make_result("SPEC_VAGUE_SCOPE", severity="MEDIUM")]
        writer.write_flags(tender_id=1, results=results, spec_text="some spec text")

        assert mock_highlighter.highlight.call_count == 2

    def test_highlight_called_with_correct_args(self, writer, mock_models, mock_highlighter):
        """ClauseHighlighter.highlight receives spec_text, flag_type, trigger_data."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        trigger = {"matched_tender_id": 42, "similarity_score": 0.91}
        RedFlag.objects.create.return_value = _make_red_flag("SPEC_TAILORING")

        writer.write_flags(
            tender_id=1,
            results=[_make_result("SPEC_TAILORING", trigger_data=trigger)],
            spec_text="spec text here",
        )

        mock_highlighter.highlight.assert_called_once_with(
            spec_text="spec text here",
            flag_type="SPEC_TAILORING",
            trigger_data=trigger,
        )

    def test_clause_highlights_created_for_each_highlight(self, writer, mock_models, mock_highlighter):
        """One SpecClauseHighlight is created per ClauseHighlight returned."""
        RedFlag, _, SpecClauseHighlight = mock_models
        RedFlag.objects.filter.return_value = []
        flag = _make_red_flag("SPEC_TAILORING", pk=1)
        RedFlag.objects.create.return_value = flag

        # Simulate two highlights returned
        h1 = MagicMock()
        h1.sentence_text = "Sentence one."
        h1.sentence_index = 0
        h1.relevance_score = 0.95
        h1.reason = "Highly similar to fraud corpus"

        h2 = MagicMock()
        h2.sentence_text = "Sentence two."
        h2.sentence_index = 1
        h2.relevance_score = 0.80
        h2.reason = "Similar to matched tender"

        mock_highlighter.highlight.return_value = [h1, h2]

        writer.write_flags(tender_id=3, results=[_make_result()], spec_text="Sentence one. Sentence two.")

        assert SpecClauseHighlight.objects.create.call_count == 2

    def test_clause_highlight_fields(self, writer, mock_models, mock_highlighter):
        """SpecClauseHighlight is created with correct field values."""
        RedFlag, _, SpecClauseHighlight = mock_models
        RedFlag.objects.filter.return_value = []
        flag = _make_red_flag("SPEC_TAILORING", pk=5)
        RedFlag.objects.create.return_value = flag

        h = MagicMock()
        h.sentence_text = "The supplier must be XYZ certified."
        h.sentence_index = 2
        h.relevance_score = 0.88
        h.reason = "Highly similar to fraud corpus entry"
        mock_highlighter.highlight.return_value = [h]

        writer.write_flags(tender_id=3, results=[_make_result()], spec_text="some text")

        SpecClauseHighlight.objects.create.assert_called_once_with(
            tender_id=3,
            red_flag=flag,
            sentence_text="The supplier must be XYZ certified.",
            sentence_index=2,
            relevance_score=0.88,
            reason="Highly similar to fraud corpus entry",
        )

    def test_reason_truncated_to_500_chars(self, writer, mock_models, mock_highlighter):
        """reason field is truncated to 500 characters."""
        RedFlag, _, SpecClauseHighlight = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.return_value = _make_red_flag()

        h = MagicMock()
        h.sentence_text = "A sentence."
        h.sentence_index = 0
        h.relevance_score = 0.5
        h.reason = "x" * 600  # 600 chars — should be truncated
        mock_highlighter.highlight.return_value = [h]

        writer.write_flags(tender_id=1, results=[_make_result()], spec_text="A sentence.")

        _, kwargs = SpecClauseHighlight.objects.create.call_args
        assert len(kwargs["reason"]) == 500

    def test_no_highlights_created_when_highlighter_returns_empty(self, writer, mock_models, mock_highlighter):
        """No SpecClauseHighlight records created when highlighter returns []."""
        RedFlag, _, SpecClauseHighlight = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.return_value = _make_red_flag()
        mock_highlighter.highlight.return_value = []

        writer.write_flags(tender_id=1, results=[_make_result()])

        SpecClauseHighlight.objects.create.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: SpecAnalysisResult update (Requirements 4.3, 5.3, 6.5, 7.4)
# ---------------------------------------------------------------------------

class TestUpdateSpecAnalysisResult:
    def test_tailoring_fields_updated(self, writer, mock_models, mock_highlighter):
        """tailoring_similarity and tailoring_matched_tender_id are set."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.return_value = _make_red_flag("SPEC_TAILORING")

        sar = _make_spec_analysis_result()
        result = _make_result(
            "SPEC_TAILORING",
            score=0.91,
            trigger_data={"matched_tender_id": 42, "similarity_score": 0.91},
        )
        writer.write_flags(tender_id=1, results=[result], spec_analysis_result=sar)

        assert sar.tailoring_similarity == pytest.approx(0.91)
        assert sar.tailoring_matched_tender_id == 42

    def test_copy_paste_fields_updated(self, writer, mock_models, mock_highlighter):
        """copy_paste_similarity and copy_paste_matched_tender_id are set."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.return_value = _make_red_flag("SPEC_COPY_PASTE")

        sar = _make_spec_analysis_result()
        result = _make_result(
            "SPEC_COPY_PASTE",
            score=0.95,
            trigger_data={"matched_tender_id": 77, "similarity_score": 0.95},
        )
        writer.write_flags(tender_id=1, results=[result], spec_analysis_result=sar)

        assert sar.copy_paste_similarity == pytest.approx(0.95)
        assert sar.copy_paste_matched_tender_id == 77

    def test_vagueness_score_updated(self, writer, mock_models, mock_highlighter):
        """vagueness_score is set from SPEC_VAGUE_SCOPE result."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.return_value = _make_red_flag("SPEC_VAGUE_SCOPE")

        sar = _make_spec_analysis_result()
        result = _make_result("SPEC_VAGUE_SCOPE", severity="MEDIUM", score=0.78)
        writer.write_flags(tender_id=1, results=[result], spec_analysis_result=sar)

        assert sar.vagueness_score == pytest.approx(0.78)

    def test_unusual_restriction_score_updated(self, writer, mock_models, mock_highlighter):
        """unusual_restriction_score is set from SPEC_UNUSUAL_RESTRICTION result."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.return_value = _make_red_flag("SPEC_UNUSUAL_RESTRICTION")

        sar = _make_spec_analysis_result()
        result = _make_result("SPEC_UNUSUAL_RESTRICTION", severity="MEDIUM", score=0.65)
        writer.write_flags(tender_id=1, results=[result], spec_analysis_result=sar)

        assert sar.unusual_restriction_score == pytest.approx(0.65)

    def test_flags_raised_set_to_created_flag_types(self, writer, mock_models, mock_highlighter):
        """flags_raised is set to the list of flag_type strings from created flags."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        flag1 = _make_red_flag("SPEC_TAILORING", pk=1)
        flag2 = _make_red_flag("SPEC_VAGUE_SCOPE", pk=2)
        RedFlag.objects.create.side_effect = [flag1, flag2]

        sar = _make_spec_analysis_result()
        results = [
            _make_result("SPEC_TAILORING"),
            _make_result("SPEC_VAGUE_SCOPE", severity="MEDIUM"),
        ]
        writer.write_flags(tender_id=1, results=results, spec_analysis_result=sar)

        assert set(sar.flags_raised) == {"SPEC_TAILORING", "SPEC_VAGUE_SCOPE"}

    def test_sar_save_called_with_update_fields(self, writer, mock_models, mock_highlighter):
        """SpecAnalysisResult.save is called with update_fields."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.return_value = _make_red_flag("SPEC_TAILORING")

        sar = _make_spec_analysis_result()
        result = _make_result("SPEC_TAILORING", trigger_data={"matched_tender_id": 1})
        writer.write_flags(tender_id=1, results=[result], spec_analysis_result=sar)

        sar.save.assert_called_once()
        _, kwargs = sar.save.call_args
        assert "update_fields" in kwargs
        assert "flags_raised" in kwargs["update_fields"]
        assert "tailoring_similarity" in kwargs["update_fields"]

    def test_no_sar_update_when_not_provided(self, writer, mock_models, mock_highlighter):
        """SpecAnalysisResult is not touched when spec_analysis_result=None."""
        RedFlag, SpecAnalysisResult, _ = mock_models
        RedFlag.objects.filter.return_value = []
        RedFlag.objects.create.return_value = _make_red_flag()

        writer.write_flags(tender_id=1, results=[_make_result()])

        # SpecAnalysisResult model class should not be called
        SpecAnalysisResult.objects.create.assert_not_called()
        SpecAnalysisResult.objects.filter.assert_not_called()

    def test_flags_raised_empty_when_no_results(self, writer, mock_models, mock_highlighter):
        """flags_raised is [] when results is empty."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []

        sar = _make_spec_analysis_result()
        writer.write_flags(tender_id=1, results=[], spec_analysis_result=sar)

        assert sar.flags_raised == []


# ---------------------------------------------------------------------------
# Tests: error resilience
# ---------------------------------------------------------------------------

class TestErrorResilience:
    def test_continues_after_redflag_create_failure(self, writer, mock_models, mock_highlighter):
        """If RedFlag.create raises, remaining results are still processed."""
        RedFlag, _, _ = mock_models
        RedFlag.objects.filter.return_value = []
        # First create raises, second succeeds
        flag2 = _make_red_flag("SPEC_VAGUE_SCOPE", pk=2)
        RedFlag.objects.create.side_effect = [Exception("DB error"), flag2]

        results = [
            _make_result("SPEC_TAILORING"),
            _make_result("SPEC_VAGUE_SCOPE", severity="MEDIUM"),
        ]
        flags = writer.write_flags(tender_id=1, results=results)

        # Only the second flag should be in the returned list
        assert len(flags) == 1
        assert flags[0].flag_type == "SPEC_VAGUE_SCOPE"

    def test_continues_after_highlighter_failure(self, writer, mock_models, mock_highlighter):
        """If ClauseHighlighter raises, the flag is still returned."""
        RedFlag, _, SpecClauseHighlight = mock_models
        RedFlag.objects.filter.return_value = []
        flag = _make_red_flag("SPEC_TAILORING", pk=1)
        RedFlag.objects.create.return_value = flag
        mock_highlighter.highlight.side_effect = Exception("Highlighter error")

        flags = writer.write_flags(tender_id=1, results=[_make_result()])

        assert len(flags) == 1
        SpecClauseHighlight.objects.create.assert_not_called()
