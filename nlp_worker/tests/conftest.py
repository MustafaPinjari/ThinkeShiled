"""
pytest configuration for nlp_worker unit tests.

Provides a shared SpecEmbedder fixture so the model is loaded once
per test session rather than once per test.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def embedder():
    """Return a real SpecEmbedder instance (model loaded once per session)."""
    from nlp_worker.embedder import SpecEmbedder
    return SpecEmbedder()
