"""
Property-based tests for SpecEmbedder.

**Property 1: Identical spec texts produce similarity score of 1.0**
**Validates: Requirements 3.2, 3.3**

**Property 2: Similarity is symmetric**
**Validates: Requirements 3.2**

Uses hypothesis with st.text(min_size=1, max_size=500) strategies.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two L2-normalized vectors (= dot product)."""
    return float(np.dot(a, b))


# ---------------------------------------------------------------------------
# Unit tests — specific examples
# ---------------------------------------------------------------------------

class TestEmbedUnit:
    def test_empty_string_returns_zero_vector(self, embedder):
        result = embedder.embed("")
        assert result.shape == (384,)
        assert result.dtype == np.float32
        assert np.all(result == 0.0)

    def test_none_returns_zero_vector(self, embedder):
        result = embedder.embed(None)
        assert result.shape == (384,)
        assert result.dtype == np.float32
        assert np.all(result == 0.0)

    def test_non_empty_returns_unit_vector(self, embedder):
        result = embedder.embed("Supply of laboratory equipment.")
        norm = np.linalg.norm(result)
        assert abs(norm - 1.0) < 1e-5

    def test_output_shape_and_dtype(self, embedder):
        result = embedder.embed("Test specification text.")
        assert result.shape == (384,)
        assert result.dtype == np.float32

    def test_deterministic_same_text(self, embedder):
        text = "The supplier must deliver within 7 days."
        v1 = embedder.embed(text)
        v2 = embedder.embed(text)
        np.testing.assert_array_equal(v1, v2)

    def test_embed_sentences_empty_returns_empty_list(self, embedder):
        assert embedder.embed_sentences("") == []

    def test_embed_sentences_none_returns_empty_list(self, embedder):
        assert embedder.embed_sentences(None) == []

    def test_embed_sentences_returns_tuples(self, embedder):
        text = "First sentence. Second sentence."
        result = embedder.embed_sentences(text)
        assert len(result) >= 1
        for sentence, vec in result:
            assert isinstance(sentence, str)
            assert vec.shape == (384,)
            assert vec.dtype == np.float32
            assert abs(np.linalg.norm(vec) - 1.0) < 1e-5

    def test_embed_batch_empty_list(self, embedder):
        assert embedder.embed_batch([]) == []

    def test_embed_batch_with_empty_strings(self, embedder):
        results = embedder.embed_batch(["", "hello world", ""])
        assert len(results) == 3
        assert np.all(results[0] == 0.0)
        assert abs(np.linalg.norm(results[1]) - 1.0) < 1e-5
        assert np.all(results[2] == 0.0)

    def test_embed_batch_matches_individual_embed(self, embedder):
        texts = ["First text.", "Second text.", "Third text."]
        batch_results = embedder.embed_batch(texts)
        for text, batch_vec in zip(texts, batch_results):
            individual_vec = embedder.embed(text)
            np.testing.assert_allclose(batch_vec, individual_vec, atol=1e-5)


# ---------------------------------------------------------------------------
# Property 1: Identical spec texts produce similarity score of 1.0
# Validates: Requirements 3.2, 3.3
# ---------------------------------------------------------------------------

@settings(max_examples=10, deadline=10_000)
@given(text=st.text(min_size=1, max_size=100))
def test_property_identical_texts_similarity_is_one(embedder, text):
    """
    **Property 1: Identical spec texts produce similarity score of 1.0**
    **Validates: Requirements 3.2, 3.3**

    For any non-empty spec text t, embedding t twice and computing cosine
    similarity must yield exactly 1.0 (within floating-point tolerance).
    This validates both L2-normalization (3.2) and determinism (3.3).
    """
    v1 = embedder.embed(text)
    v2 = embedder.embed(text)

    # Both vectors must be unit vectors (L2-normalized)
    assert abs(np.linalg.norm(v1) - 1.0) < 1e-5, (
        f"First embedding not unit-normalized: norm={np.linalg.norm(v1)}"
    )
    assert abs(np.linalg.norm(v2) - 1.0) < 1e-5, (
        f"Second embedding not unit-normalized: norm={np.linalg.norm(v2)}"
    )

    # Identical inputs must produce identical outputs (determinism)
    sim = cosine_similarity(v1, v2)
    assert sim == pytest.approx(1.0, abs=1e-5), (
        f"Cosine similarity of identical texts is {sim}, expected 1.0"
    )


# ---------------------------------------------------------------------------
# Property 2: Similarity is symmetric
# Validates: Requirements 3.2
# ---------------------------------------------------------------------------

@settings(max_examples=10, deadline=10_000)
@given(
    a=st.text(min_size=1, max_size=100),
    b=st.text(min_size=1, max_size=100),
)
def test_property_similarity_is_symmetric(embedder, a, b):
    """
    **Property 2: Similarity is symmetric**
    **Validates: Requirements 3.2**

    For any two spec texts a and b:
    sim(embed(a), embed(b)) == sim(embed(b), embed(a))

    This follows from the mathematical symmetry of dot product on
    L2-normalized vectors, but we verify it holds in practice.
    """
    va = embedder.embed(a)
    vb = embedder.embed(b)

    sim_ab = cosine_similarity(va, vb)
    sim_ba = cosine_similarity(vb, va)

    assert sim_ab == pytest.approx(sim_ba, abs=1e-6), (
        f"Similarity not symmetric: sim(a,b)={sim_ab}, sim(b,a)={sim_ba}"
    )
