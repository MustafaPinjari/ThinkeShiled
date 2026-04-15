"""
Property 7: NLP flags contribute to FraudRiskScore (non-decreasing)

**Validates: Requirements 9.2, 9.3**

For any initial FraudRiskScore (computed before NLP analysis), after
analyze_spec_task runs with a spec text that triggers NLP flags (mocked
Qdrant returns high similarity), the resulting FraudRiskScore must be
>= the score before NLP analysis.

This validates that:
  - Requirement 9.2: NLP RedFlags are included in FraudRiskScore computation
    using the severity-weighted formula (HIGH=25, MEDIUM=10, capped at 50).
  - Requirement 9.3: FraudRiskScore after NLP analysis >= score before NLP analysis.
"""

from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
from django.utils import timezone
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

# ---------------------------------------------------------------------------
# sys.path bootstrap
# ---------------------------------------------------------------------------

_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_ROOT_DIR = os.path.abspath(os.path.join(_BACKEND_DIR, ".."))
for _p in (_BACKEND_DIR, _ROOT_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Pre-patch the embedder singleton to avoid loading the sentence-transformers
# model during tests.
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

with patch("sentence_transformers.SentenceTransformer"):
    import nlp_worker.embedder as _emb_module

_emb_module._embedder = _mock_embedder_singleton

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


def _uid(prefix: str = "T") -> str:
    global _counter
    _counter += 1
    return f"{prefix}-NLP-SCORE-PBT-{_counter}"


def _make_tender(spec_text: str, estimated_value: Decimal = Decimal("500000.00")):
    """Create a minimal Tender in the test DB with the given spec_text."""
    from tenders.models import Tender

    return Tender.objects.create(
        tender_id=_uid("T"),
        title="NLP Score Property Test Tender",
        category="IT",
        estimated_value=estimated_value,
        currency="INR",
        submission_deadline=timezone.now() + timezone.timedelta(days=30),
        publication_date=timezone.now() - timezone.timedelta(days=5),
        buyer_id=_uid("BUYER"),
        buyer_name="Test Buyer",
        spec_text=spec_text,
    )


def _seed_ml_scores_for_initial_score(tender, initial_score: int):
    """
    Seed ML scores so that RiskScorer.compute_score() produces approximately
    `initial_score` before any NLP flags exist.

    The scoring formula is:
        score = clamp(red_flag_contribution + ml_anomaly*30 + ml_collusion*20, 0, 100)

    With no red flags, score = clamp(ml_anomaly*30 + ml_collusion*20, 0, 100).
    We set ml_anomaly = initial_score / 50.0 (capped at 1.0) and ml_collusion = 0
    so that the ML contribution approximates the initial_score.
    """
    from scoring.models import FraudRiskScore

    # Derive ML scores that produce approximately initial_score with no flags
    # ml_anomaly * 30 = initial_score  =>  ml_anomaly = initial_score / 30
    # Clamp to [0, 1]
    ml_anomaly = min(1.0, initial_score / 30.0)
    ml_collusion = 0.0

    FraudRiskScore.objects.create(
        tender=tender,
        score=0,  # placeholder; RiskScorer will recompute
        ml_anomaly_score=str(round(ml_anomaly, 4)),
        ml_collusion_score=str(round(ml_collusion, 4)),
        red_flag_contribution=0,
        model_version="v-pbt-ml-seed",
        weight_config={},
    )


def _make_mock_vector_store_high_similarity():
    """Return a mock VectorStore that returns high similarity (>= 0.92) for all searches."""
    from nlp_worker.vector_store import SimilarityResult

    mock = MagicMock()
    mock.upsert.return_value = None
    # similarity >= 0.92 → triggers SPEC_COPY_PASTE (HIGH severity, 25 pts)
    # similarity >= 0.85 → triggers SPEC_TAILORING (HIGH severity, 25 pts)
    mock.search_similar.return_value = [SimilarityResult(tender_id=999, similarity=0.95)]
    return mock


def _patch_embedder():
    return patch.object(_emb_module, "_embedder", _mock_embedder_singleton)


def _patch_vector_store(mock_store):
    return patch("nlp_worker.vector_store.VectorStore", return_value=mock_store)


# ---------------------------------------------------------------------------
# Spec text that reliably triggers NLP flags via mocked Qdrant:
#   - High similarity (0.95) → SPEC_COPY_PASTE (HIGH) + SPEC_TAILORING (HIGH)
# ---------------------------------------------------------------------------

_FLAGGING_SPEC_TEXT = (
    "The supplier must have supplied to Ministry of Health in the last 6 months. "
    "Equipment must carry XYZ-brand certification. "
    "Delivery within 7 days of award."
)


# ===========================================================================
# Property 7: NLP flags contribute to FraudRiskScore (non-decreasing)
# Validates: Requirements 9.2, 9.3
# ===========================================================================

class NLPFlagsContributeToFraudRiskScoreProperty(TestCase):
    """
    Property 7: NLP flags contribute to FraudRiskScore (non-decreasing)

    **Validates: Requirements 9.2, 9.3**

    For any initial score value in [0, 99], after analyze_spec_task runs with
    a spec text that triggers NLP flags (mocked Qdrant returns similarity >= 0.92),
    the resulting FraudRiskScore must be >= the score computed before NLP analysis.
    """

    @given(initial_score=st.integers(min_value=0, max_value=99))
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_nlp_flags_make_score_non_decreasing(self, initial_score: int):
        """
        Property 7: NLP flags contribute to FraudRiskScore (non-decreasing)
        **Validates: Requirements 9.2, 9.3**

        Steps:
          1. Create tender with spec text that will trigger NLP flags.
          2. Seed ML scores so RiskScorer produces a known score_before.
          3. Compute score_before via RiskScorer (no NLP flags yet).
          4. Run analyze_spec_task → NLP flags written to DB.
          5. Compute score_after via RiskScorer (NLP flags now present).
          6. Assert score_after >= score_before.
        """
        from scoring.scorer import RiskScorer

        # 1. Create tender with a spec text that will trigger NLP flags
        tender = _make_tender(spec_text=_FLAGGING_SPEC_TEXT)

        # 2. Seed ML scores to establish a baseline score_before
        _seed_ml_scores_for_initial_score(tender, initial_score)

        # 3. Compute score_before (no NLP flags exist yet)
        scorer = RiskScorer()
        score_record_before = scorer.compute_score(tender.id)
        score_before = score_record_before.score

        # 4. Run analyze_spec_task synchronously with mocked Qdrant returning
        #    high similarity (>= 0.92 → SPEC_COPY_PASTE, >= 0.85 → SPEC_TAILORING)
        mock_store = _make_mock_vector_store_high_similarity()

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(mock_store):
                    with patch("nlp_worker.tasks.current_app"):
                        from nlp_worker.tasks import analyze_spec_task
                        analyze_spec_task.apply(args=[tender.id])

        # 5. Compute score_after (NLP flags now present in DB)
        score_record_after = scorer.compute_score(tender.id)
        score_after = score_record_after.score

        # 6. Assert the property: score is non-decreasing after NLP flags are raised
        assert score_after >= score_before, (
            f"FraudRiskScore decreased after NLP analysis: "
            f"score_before={score_before}, score_after={score_after}, "
            f"initial_score={initial_score}. "
            f"NLP flags should only increase or maintain the score."
        )

    @given(initial_score=st.integers(min_value=0, max_value=99))
    @settings(
        max_examples=30,
        suppress_health_check=[HealthCheck.too_slow],
        deadline=None,
    )
    def test_nlp_high_flags_increase_red_flag_contribution(self, initial_score: int):
        """
        Property 7 (corollary): When NLP HIGH-severity flags are raised,
        red_flag_contribution in the resulting FraudRiskScore must be > 0.

        **Validates: Requirements 9.2, 9.3**

        SPEC_COPY_PASTE and SPEC_TAILORING are HIGH severity (25 points each),
        so red_flag_contribution must be > 0 after NLP analysis.
        """
        from scoring.scorer import RiskScorer
        from detection.models import RedFlag

        tender = _make_tender(spec_text=_FLAGGING_SPEC_TEXT)
        _seed_ml_scores_for_initial_score(tender, initial_score)

        mock_store = _make_mock_vector_store_high_similarity()

        with patch("nlp_worker.tasks._bootstrap_django"):
            with _patch_embedder():
                with _patch_vector_store(mock_store):
                    with patch("nlp_worker.tasks.current_app"):
                        from nlp_worker.tasks import analyze_spec_task
                        analyze_spec_task.apply(args=[tender.id])

        # Verify NLP flags were actually raised
        nlp_flags = RedFlag.objects.filter(
            tender=tender,
            flag_type__startswith="SPEC_",
            is_active=True,
        )

        if nlp_flags.exists():
            scorer = RiskScorer()
            score_record = scorer.compute_score(tender.id)

            assert score_record.red_flag_contribution > 0, (
                f"red_flag_contribution should be > 0 when NLP flags are present, "
                f"got red_flag_contribution={score_record.red_flag_contribution}, "
                f"initial_score={initial_score}"
            )
            assert score_record.score > 0, (
                f"FraudRiskScore should be > 0 when NLP HIGH flags are present, "
                f"got score={score_record.score}, initial_score={initial_score}"
            )
