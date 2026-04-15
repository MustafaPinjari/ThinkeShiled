"""
SpecEmbedder — wraps the paraphrase-multilingual-MiniLM-L12-v2 sentence-transformer model.

Produces 384-dimensional L2-normalized float32 embedding vectors.
Singleton: model is loaded once at import time.

Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
"""

from __future__ import annotations

import os
import logging
from typing import List, Tuple

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_DIM = 384


class SpecEmbedder:
    """Sentence-transformer wrapper for spec text embedding.

    Loads the model once at instantiation time from the local cache
    specified by the SENTENCE_TRANSFORMERS_HOME environment variable.
    No network requests are made during inference.
    """

    def __init__(self) -> None:
        cache_dir = os.environ.get("SENTENCE_TRANSFORMERS_HOME")
        logger.info(
            "Loading sentence-transformer model '%s' from cache: %s",
            MODEL_NAME,
            cache_dir or "<default>",
        )
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(
            MODEL_NAME,
            cache_folder=cache_dir,
        )
        logger.info("Model '%s' loaded successfully.", MODEL_NAME)

    def embed(self, text: str) -> np.ndarray:
        """Return an L2-normalized 384-dim float32 embedding vector.

        Returns a zero vector of shape (384,) for empty or None input
        without raising an exception.

        Postconditions:
        - shape == (384,), dtype == float32
        - For non-empty text: np.linalg.norm(result) ≈ 1.0 (tolerance 1e-5)
        - For empty/None text: result == np.zeros(384, dtype=float32)
        - Deterministic: identical inputs produce identical outputs
        """
        if not text:
            return np.zeros(EMBEDDING_DIM, dtype=np.float32)

        vector = self._model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        return vector.astype(np.float32)

    def embed_sentences(self, text: str) -> List[Tuple[str, np.ndarray]]:
        """Split text into sentences and embed each one.

        Uses nltk.sent_tokenize for sentence splitting.
        Returns [] for empty or None input.

        Returns:
            List of (sentence_text, embedding_vector) tuples.
        """
        if not text:
            return []

        import nltk

        try:
            sentences = nltk.sent_tokenize(text)
        except LookupError:
            # Download punkt tokenizer data if not available
            nltk.download("punkt", quiet=True)
            nltk.download("punkt_tab", quiet=True)
            sentences = nltk.sent_tokenize(text)

        if not sentences:
            return []

        vectors = self._model.encode(
            sentences,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=32,
        )
        return [
            (sentence, vec.astype(np.float32))
            for sentence, vec in zip(sentences, vectors)
        ]

    def embed_batch(self, texts: List[str]) -> List[np.ndarray]:
        """Embed a batch of texts efficiently using the model's native batching.

        Empty or None strings in the batch are replaced with zero vectors.

        Args:
            texts: List of strings to embed.

        Returns:
            List of 384-dim float32 numpy arrays, one per input text.
        """
        if not texts:
            return []

        results: List[np.ndarray] = []
        non_empty_indices: List[int] = []
        non_empty_texts: List[str] = []

        for i, text in enumerate(texts):
            if text:
                non_empty_indices.append(i)
                non_empty_texts.append(text)

        # Pre-fill with zero vectors
        output = [np.zeros(EMBEDDING_DIM, dtype=np.float32) for _ in texts]

        if non_empty_texts:
            vectors = self._model.encode(
                non_empty_texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                batch_size=64,
            )
            for idx, vec in zip(non_empty_indices, vectors):
                output[idx] = vec.astype(np.float32)

        return output


# ---------------------------------------------------------------------------
# Singleton — model loaded once at import time
# ---------------------------------------------------------------------------

_embedder: SpecEmbedder | None = None


def _get_embedder() -> SpecEmbedder:
    """Return the singleton SpecEmbedder, creating it on first call."""
    global _embedder
    if _embedder is None:
        _embedder = SpecEmbedder()
    return _embedder


# Eagerly instantiate when this module is imported by the worker process.
# In test environments the model may not be available, so we defer to
# _get_embedder() and allow tests to patch _embedder directly.
try:
    _embedder = SpecEmbedder()
except Exception as exc:  # pragma: no cover
    logger.warning(
        "SpecEmbedder could not be loaded at import time: %s. "
        "Call _get_embedder() or set nlp_worker.embedder._embedder manually.",
        exc,
    )
