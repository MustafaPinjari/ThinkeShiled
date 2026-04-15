"""
ClauseHighlighter — sentence-level explainability for NLP fraud flags.

Produces ranked ClauseHighlight objects that explain why a particular flag
was raised, analogous to SHAP feature attribution for the NLP pipeline.

Requirements: 4.4, 7.3, 8.1, 8.2, 8.4
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import log2

import nltk
import numpy as np

from nlp_worker.embedder import _get_embedder

logger = logging.getLogger(__name__)

# Flag type constants
_SPEC_TAILORING = "SPEC_TAILORING"
_SPEC_COPY_PASTE = "SPEC_COPY_PASTE"
_SPEC_UNUSUAL_RESTRICTION = "SPEC_UNUSUAL_RESTRICTION"
_SPEC_VAGUE_SCOPE = "SPEC_VAGUE_SCOPE"


@dataclass
class ClauseHighlight:
    """A single sentence-level highlight explaining a fraud flag.

    Attributes:
        sentence_text: The raw sentence text from the spec.
        sentence_index: 0-based position of the sentence in the spec.
        relevance_score: Relevance to the flag, always in [0.0, 1.0].
        reason: Human-readable explanation of why this sentence is highlighted.
    """

    sentence_text: str
    sentence_index: int
    relevance_score: float  # always in [0.0, 1.0]
    reason: str


def _clamp(value: float) -> float:
    """Clamp a float to [0.0, 1.0]."""
    return max(0.0, min(1.0, value))


def _sent_tokenize(text: str) -> list[str]:
    """Tokenize text into sentences, downloading punkt data if needed."""
    try:
        return nltk.sent_tokenize(text)
    except LookupError:
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)
        return nltk.sent_tokenize(text)


def _sentence_entropy(sentence: str) -> float:
    """Compute Shannon entropy of the word distribution in a sentence."""
    words = sentence.lower().split()
    if not words:
        return 0.0
    freq: dict[str, int] = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    n = len(words)
    return -sum((c / n) * log2(c / n) for c in freq.values() if c > 0)


class ClauseHighlighter:
    """Produce sentence-level highlights for NLP fraud flags.

    The embedder is instantiated once and reused across calls.
    """

    def __init__(self) -> None:
        self._embedder = _get_embedder()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def highlight(
        self,
        spec_text: str,
        flag_type: str,
        trigger_data: dict,
    ) -> list[ClauseHighlight]:
        """Return ranked sentence highlights explaining why a flag was raised.

        Args:
            spec_text: Full tender specification text.
            flag_type: One of SPEC_TAILORING, SPEC_COPY_PASTE,
                SPEC_UNUSUAL_RESTRICTION, SPEC_VAGUE_SCOPE.
            trigger_data: The ``trigger_data`` dict from the corresponding
                ``DetectionResult``.

        Returns:
            Ranked list of :class:`ClauseHighlight` objects (descending
            relevance_score). Returns ``[]`` for empty spec_text or unknown
            flag_type.
        """
        if not spec_text or not spec_text.strip():
            return []

        try:
            if flag_type in (_SPEC_TAILORING, _SPEC_COPY_PASTE):
                return self._highlight_similarity(spec_text, flag_type, trigger_data)
            elif flag_type == _SPEC_UNUSUAL_RESTRICTION:
                return self._highlight_unusual_restriction(trigger_data)
            elif flag_type == _SPEC_VAGUE_SCOPE:
                return self._highlight_vague_scope(spec_text)
            else:
                logger.debug("ClauseHighlighter: unknown flag_type=%r, returning [].", flag_type)
                return []
        except Exception:
            logger.exception(
                "ClauseHighlighter: unexpected error for flag_type=%r.", flag_type
            )
            return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _highlight_similarity(
        self,
        spec_text: str,
        flag_type: str,
        trigger_data: dict,
    ) -> list[ClauseHighlight]:
        """Handle SPEC_TAILORING and SPEC_COPY_PASTE via cosine similarity."""
        matched_sentences: list[str] = trigger_data.get("matched_sentences", [])
        matched_tender_id = trigger_data.get("matched_tender_id")

        sentences = _sent_tokenize(spec_text)
        if not sentences:
            return []

        # Embed spec sentences
        spec_pairs = self._embedder.embed_sentences(spec_text)
        if not spec_pairs:
            return []

        # If no matched sentences, fall back to returning top sentences by
        # their own norm (all equal for L2-normalized), so just return first 3.
        if not matched_sentences:
            highlights = [
                ClauseHighlight(
                    sentence_text=sent,
                    sentence_index=i,
                    relevance_score=0.0,
                    reason=(
                        f"Highly similar to clause in matched tender {matched_tender_id}"
                        if matched_tender_id is not None
                        else "Similar to matched fraud corpus entry"
                    ),
                )
                for i, (sent, _) in enumerate(spec_pairs)
            ]
            return highlights[:3]

        # Embed matched sentences from the fraud corpus entry
        matched_vecs: list[np.ndarray] = self._embedder.embed_batch(matched_sentences)

        results: list[ClauseHighlight] = []
        for i, (sent, spec_vec) in enumerate(spec_pairs):
            # Max cosine similarity against all matched sentences
            # For L2-normalized vectors: cosine_sim = dot product
            max_sim = max(
                (float(np.dot(spec_vec, m_vec)) for m_vec in matched_vecs),
                default=0.0,
            )
            score = _clamp(max_sim)
            reason = (
                f"Highly similar to clause in matched tender {matched_tender_id}"
                if matched_tender_id is not None
                else "Highly similar to clause in matched fraud corpus entry"
            )
            results.append(
                ClauseHighlight(
                    sentence_text=sent,
                    sentence_index=i,
                    relevance_score=score,
                    reason=reason,
                )
            )

        results.sort(key=lambda h: h.relevance_score, reverse=True)
        return results[:3]

    def _highlight_unusual_restriction(
        self,
        trigger_data: dict,
    ) -> list[ClauseHighlight]:
        """Handle SPEC_UNUSUAL_RESTRICTION from pre-computed anomalous_clauses."""
        anomalous_clauses: list[dict] = trigger_data.get("anomalous_clauses", [])
        if not anomalous_clauses:
            return []

        highlights: list[ClauseHighlight] = []
        for clause in anomalous_clauses:
            try:
                sentence_text = clause["sentence_text"]
                sentence_index = clause["sentence_index"]
                distance = float(clause["distance"])
            except (KeyError, TypeError, ValueError):
                logger.debug(
                    "ClauseHighlighter: malformed anomalous_clause entry: %r", clause
                )
                continue

            score = _clamp(distance)
            reason = f"Anomalous clause: distance {distance:.3f} from category centroid"
            highlights.append(
                ClauseHighlight(
                    sentence_text=sentence_text,
                    sentence_index=sentence_index,
                    relevance_score=score,
                    reason=reason,
                )
            )

        highlights.sort(key=lambda h: h.relevance_score, reverse=True)
        return highlights

    def _highlight_vague_scope(self, spec_text: str) -> list[ClauseHighlight]:
        """Handle SPEC_VAGUE_SCOPE by ranking sentences by vagueness."""
        sentences = _sent_tokenize(spec_text)
        if not sentences:
            return []

        highlights: list[ClauseHighlight] = []
        for i, sent in enumerate(sentences):
            words = sent.lower().split()
            wc = len(words)
            ent = _sentence_entropy(sent)

            # Vagueness: shorter + lower entropy = more vague
            vagueness = (1.0 - min(wc / 50.0, 1.0)) * 0.5 + (1.0 - min(ent / 5.0, 1.0)) * 0.5
            score = _clamp(vagueness)
            reason = f"Short, low-entropy clause (word_count={wc}, entropy={ent:.2f})"
            highlights.append(
                ClauseHighlight(
                    sentence_text=sent,
                    sentence_index=i,
                    relevance_score=score,
                    reason=reason,
                )
            )

        highlights.sort(key=lambda h: h.relevance_score, reverse=True)
        return highlights[:3]
