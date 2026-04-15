# Implementation Plan: NLP Tender Specification Analysis

## Overview

Implement a parallel NLP fraud-detection pipeline for Ten2derShield that embeds tender specification
text using a multilingual sentence-transformer model and applies four detectors (tailoring,
copy-paste, vague scope, unusual restriction). The pipeline runs as a separate Celery worker
(`nlp-worker`), writes `RedFlag` records and `SpecClauseHighlight` explainability records, and
contributes to the existing `FraudRiskScore`.

Tasks are ordered foundation-first: data models → NLP components → detectors → flag writer →
Celery task → API integration → Docker Compose.

---

## Tasks

- [x] 1. Extend data models and create migrations
  - [x] 1.1 Add `spec_text` and `spec_language` fields to the `Tender` model
    - In `backend/tenders/models.py`, add:
      - `spec_text = models.TextField(blank=True, default="")`
      - `spec_language = models.CharField(max_length=10, blank=True, default="")`
    - Run `python manage.py makemigrations tenders` to generate the migration
    - _Requirements: 1.1, 1.3_

  - [x] 1.2 Add four new `FlagType` choices to `backend/detection/models.py`
    - Append to `FlagType(models.TextChoices)`:
      - `SPEC_TAILORING = "SPEC_TAILORING", "Specification Tailoring"`
      - `SPEC_COPY_PASTE = "SPEC_COPY_PASTE", "Copy-Paste Fraud"`
      - `SPEC_VAGUE_SCOPE = "SPEC_VAGUE_SCOPE", "Vague Scope"`
      - `SPEC_UNUSUAL_RESTRICTION = "SPEC_UNUSUAL_RESTRICTION", "Unusual Restriction"`
    - Run `python manage.py makemigrations detection` to generate the migration
    - _Requirements: 9.1_

  - [x] 1.3 Create the `backend/nlp/` Django app with `SpecAnalysisResult` and `SpecClauseHighlight` models
    - Create `backend/nlp/__init__.py`, `backend/nlp/apps.py`
    - Create `backend/nlp/models.py` with `SpecAnalysisResult` and `SpecClauseHighlight` exactly as specified in the design document
    - Register `nlp` in `INSTALLED_APPS` in `backend/config/settings.py`
    - Run `python manage.py makemigrations nlp` to generate the initial migration
    - _Requirements: 2.3, 2.6, 8.1, 8.2, 8.3, 8.4_

- [x] 2. Implement `SpecEmbedder` in `nlp_worker/embedder.py`
  - Create `nlp_worker/__init__.py` and `nlp_worker/embedder.py`
  - Implement `SpecEmbedder` class as a singleton (model loaded once at import time):
    - `embed(text: str) -> np.ndarray` — returns L2-normalized 384-dim float32 vector; returns `np.zeros(384, dtype=np.float32)` for empty/None input without raising
    - `embed_sentences(text: str) -> list[tuple[str, np.ndarray]]` — splits text into sentences using `nltk.sent_tokenize` and embeds each; returns `[]` for empty input
    - `embed_batch(texts: list[str]) -> list[np.ndarray]` — batched embedding for bulk ingestion
  - Model: `paraphrase-multilingual-MiniLM-L12-v2`, loaded from local cache (`SENTENCE_TRANSFORMERS_HOME` env var)
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [ ]* 2.1 Write property tests for `SpecEmbedder`
    - **Property 1: Identical spec texts produce similarity score of 1.0**
    - **Validates: Requirements 3.2, 3.3**
    - **Property 2: Similarity is symmetric**
    - **Validates: Requirements 3.2**
    - Use `hypothesis` with `st.text(min_size=1, max_size=500)` strategies
    - Test file: `nlp_worker/tests/test_embedder_properties.py`

- [x] 3. Implement `VectorStore` in `nlp_worker/vector_store.py`
  - Create `nlp_worker/vector_store.py` wrapping `qdrant_client.QdrantClient`
  - Collection name: `tender_specs`; distance metric: `Cosine`
  - Implement:
    - `upsert(tender_id, vector, payload)` — insert or update embedding point
    - `search_similar(vector, top_k, filter_payload) -> list[SimilarityResult]` — returns sorted descending by score
    - `mark_fraud_corpus(tender_id, confirmed_fraud)` — updates `is_fraud_corpus` and `confirmed_fraud` payload fields
  - Auto-create collection on first use if it does not exist
  - Define `SimilarityResult` dataclass: `tender_id: int`, `similarity: float`
  - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [x] 4. Implement the four detectors in `nlp_worker/detectors/`
  - Create `nlp_worker/detectors/__init__.py`
  - Define shared `DetectionResult` dataclass in `nlp_worker/detectors/__init__.py`:
    `flag_type: str`, `severity: str`, `score: float`, `trigger_data: dict`

  - [x] 4.1 Implement `TailoringDetector` in `nlp_worker/detectors/tailoring.py`
    - `detect(tender_id, vector, category) -> DetectionResult | None`
    - Search fraud corpus (`filter_payload={"is_fraud_corpus": True}`, `top_k=5`)
    - Return `DetectionResult(flag_type="SPEC_TAILORING", severity="HIGH", ...)` if `max_similarity >= 0.85`, else `None`
    - `trigger_data` must include: `matched_tender_id`, `similarity_score`, `threshold`, `matched_sentences`
    - _Requirements: 4.1, 4.2, 4.3_

  - [x] 4.2 Implement `CopyPasteDetector` in `nlp_worker/detectors/copy_paste.py`
    - `detect(tender_id, vector) -> DetectionResult | None`
    - Search all fraud corpus entries (`is_fraud_corpus=True` OR `confirmed_fraud=True`), `top_k=10`
    - Return `DetectionResult(flag_type="SPEC_COPY_PASTE", severity="HIGH", ...)` if `max_similarity >= 0.92`, else `None`
    - `trigger_data` must include: `matched_tender_id`, `similarity_score`, `threshold`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 4.3 Write property tests for `CopyPasteDetector`
    - **Property 3: SPEC_COPY_PASTE flag implies `copy_paste_similarity >= 0.92`**
    - **Validates: Requirements 5.1, 5.4**
    - **Property 4: Absence of SPEC_COPY_PASTE flag implies `copy_paste_similarity < 0.92` or `None`**
    - **Validates: Requirements 5.2, 5.5**
    - Mock `VectorStore.search_similar` with controlled similarity values using `hypothesis`
    - Test file: `nlp_worker/tests/test_copy_paste_properties.py`

  - [x] 4.4 Implement `VagueScopeDetector` in `nlp_worker/detectors/vague_scope.py`
    - `detect(tender_id, spec_text, estimated_value, category) -> DetectionResult | None`
    - Implement `compute_vagueness_score(spec_text, estimated_value, category) -> float` as a pure function (no I/O) — this is the testable unit
    - Composite score formula (from design): `(1 - min(ttr,1)) * 0.35 + (1 - min(entropy/10,1)) * 0.35 + (1 - min(value_normalized_length/100,1)) * 0.30`, clamped to `[0.0, 1.0]`
    - Default category baseline: `0.70`; load per-category baseline from DB if available
    - `trigger_data` must include: `vagueness_score`, `word_count`, `type_token_ratio`, `entropy`, `value_normalized_length`, `category_baseline`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 4.5 Write property tests for `VagueScopeDetector`
    - **Property 5: Vagueness score is monotonically related to spec length and entropy**
    - **Validates: Requirements 6.1, 6.4**
    - Use `hypothesis` to generate pairs of texts where `word_count(s1) < word_count(s2)` and `entropy(s1) <= entropy(s2)` and assert `vagueness_score(s1) >= vagueness_score(s2)`
    - Test the pure `compute_vagueness_score` function directly (no mocking needed)
    - Test file: `nlp_worker/tests/test_vague_scope_properties.py`

  - [x] 4.6 Implement `UnusualRestrictionDetector` in `nlp_worker/detectors/unusual_restriction.py`
    - `detect(tender_id, sentences, category) -> DetectionResult | None`
    - Compute cosine distance of each sentence embedding from the category centroid
    - Flag sentences exceeding the category's 95th-percentile threshold
    - Return `DetectionResult(flag_type="SPEC_UNUSUAL_RESTRICTION", severity="MEDIUM", ...)` with top anomalous clauses in `trigger_data`
    - Store overall anomaly score in `DetectionResult.score`
    - _Requirements: 7.1, 7.2, 7.4_

- [x] 5. Checkpoint — unit test all detectors in isolation
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement `ClauseHighlighter` in `nlp_worker/highlighter.py`
  - `highlight(spec_text, flag_type, trigger_data) -> list[ClauseHighlight]`
  - Define `ClauseHighlight` dataclass: `sentence_text: str`, `sentence_index: int`, `relevance_score: float`, `reason: str`
  - For `SPEC_TAILORING` / `SPEC_COPY_PASTE`: rank sentences by cosine similarity to matched fraud corpus entry; top 3 sentences
  - For `SPEC_UNUSUAL_RESTRICTION`: rank sentences by distance from category centroid (descending)
  - For `SPEC_VAGUE_SCOPE`: highlight shortest, lowest-entropy sentences as most relevant
  - Ensure `relevance_score` is always in `[0.0, 1.0]`
  - _Requirements: 4.4, 7.3, 8.1, 8.2, 8.4_

- [x] 7. Implement `NLPFlagWriter` in `nlp_worker/flag_writer.py`
  - `write_flags(tender_id, results: list[DetectionResult]) -> list[RedFlag]`
  - Before writing: clear all previously active NLP `RedFlag` records for `tender_id` (flag types starting with `SPEC_`) using `RedFlag.clear()`
  - For each non-None `DetectionResult`: create one `RedFlag` record with `flag_type`, `severity`, `trigger_data`, `rule_version="nlp-1.0"`
  - After creating each `RedFlag`: call `ClauseHighlighter.highlight()` and create `SpecClauseHighlight` records linked to the flag
  - Update `SpecAnalysisResult` fields: `tailoring_similarity`, `tailoring_matched_tender_id`, `copy_paste_similarity`, `copy_paste_matched_tender_id`, `vagueness_score`, `unusual_restriction_score`, `flags_raised`
  - _Requirements: 4.3, 5.3, 6.5, 7.4, 8.1, 9.4_

- [x] 8. Implement the main `analyze_spec_task` Celery task in `nlp_worker/tasks.py`
  - Follow the `ml_worker/tasks.py` pattern: bootstrap Django with `_bootstrap_django()`, use `@shared_task`
  - Task name: `"nlp_worker.analyze_spec_task"`, `bind=True`, `max_retries=3`, `default_retry_delay=60`
  - Implement the full algorithm from the design document:
    1. Fetch `Tender` by `tender_id`; if `spec_text` is empty → insert `SpecAnalysisResult(error="empty_spec")` and return
    2. Detect language with `langdetect`; update `Tender.spec_language`
    3. Embed full spec and sentences via `SpecEmbedder`
    4. Upsert embedding to `VectorStore`; on `QdrantException` → set `error="qdrant_unavailable"`, skip vector detectors, still run `VagueScopeDetector`
    5. Run all four detectors; catch per-detector exceptions individually (log + continue)
    6. Call `NLPFlagWriter.write_flags()`
    7. Insert `SpecAnalysisResult` with all scores, `flags_raised`, `analysis_duration_ms`
    8. If any flags raised: `current_app.send_task("ml_worker.score_tender", args=[tender_id])`
    9. On Qdrant retry exhaustion: write `AuditLog` entry with tender ID, task name, failure reason
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 1.4, 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 9. Checkpoint — end-to-end task test with mocked Qdrant
  - Ensure all tests pass, ask the user if questions arise.

- [x] 10. Update `TenderSerializer` and `TenderCreateView` for `spec_text`
  - In `backend/tenders/serializers.py`:
    - Add `spec_text = serializers.CharField(max_length=100_000, required=False, allow_blank=True, default="")` to `TenderSerializer`
    - Add `spec_text` to `Meta.fields`
    - In `validate`, sanitize `spec_text` with `bleach.clean` (strip tags)
    - Raise `serializers.ValidationError` with code `VALIDATION_ERROR` if `len(spec_text) > 100_000`
  - In `backend/tenders/views.py` `TenderCreateView.post()`:
    - After `tender = serializer.save()`, enqueue: `current_app.send_task("nlp_worker.analyze_spec_task", args=[tender.id])`
  - _Requirements: 1.1, 1.2, 2.1_

  - [ ]* 10.1 Write property test for empty spec producing no NLP flags
    - **Property 6: Empty spec never produces a false positive flag**
    - **Validates: Requirements 2.2, 11.5**
    - Use `hypothesis` with `st.just("")` and `st.none()` strategies; call `analyze_spec_task` synchronously (`CELERY_TASK_ALWAYS_EAGER=True`)
    - Assert `SpecAnalysisResult.flags_raised == []` and no `SPEC_*` `RedFlag` records exist
    - Test file: `backend/tests/test_nlp_empty_spec_property.py`

- [x] 11. Update `TenderCSVUploadView` to accept optional `spec_text` column
  - In `backend/tenders/views.py` `TenderCSVUploadView.post()`:
    - In the per-row `data` dict, add: `"spec_text": row.get("spec_text", "").strip()`
    - After `Tender.objects.bulk_create(batch)`, enqueue `analyze_spec_task` for each created tender that has non-empty `spec_text`
  - _Requirements: 1.1, 2.1_

- [x] 12. Add `PATCH /api/v1/tenders/{id}/` endpoint for spec text updates
  - Create `TenderSpecUpdateView` in `backend/tenders/views.py`:
    - `PATCH /api/v1/tenders/{id}/` — accepts `spec_text` field (ADMIN only)
    - Validate `spec_text` length <= 100,000 chars
    - Save updated `spec_text` to `Tender`; clear `spec_language` (will be re-detected)
    - Enqueue `analyze_spec_task` for the tender
    - Write `AuditLog` entry
  - Register route in `backend/tenders/urls.py`
  - _Requirements: 1.5_

- [x] 13. Add `GET /api/v1/tenders/{id}/spec-analysis/` endpoint
  - Create `TenderSpecAnalysisView` in `backend/tenders/views.py` (or `backend/nlp/views.py`):
    - Permission: `IsAuditorOrAdmin`
    - Return the latest `SpecAnalysisResult` for the tender with all score fields and `flags_raised`
    - Include nested `SpecClauseHighlight` records grouped by `flag_type`, ordered by `-relevance_score`
    - Return 404 if no analysis exists yet
  - Create `SpecAnalysisResultSerializer` and `SpecClauseHighlightSerializer` in `backend/nlp/serializers.py`
  - Register route in `backend/tenders/urls.py` as `<int:pk>/spec-analysis/`
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 14. Add `POST /api/v1/tenders/{id}/mark-fraud-corpus/` endpoint
  - Create `TenderMarkFraudCorpusView` in `backend/tenders/views.py`:
    - Permission: `IsAdminRole` only
    - Accept `confirmed_fraud: bool` in request body
    - Call `VectorStore().mark_fraud_corpus(tender_id=tender.id, confirmed_fraud=confirmed_fraud)`
    - Write `AuditLog` entry
    - Return 200 on success; 404 if tender not found; 503 if Qdrant unreachable
  - Register route in `backend/tenders/urls.py` as `<int:pk>/mark-fraud-corpus/`
  - _Requirements: 10.4, 10.5_

- [x] 15. Checkpoint — run full backend test suite
  - Ensure all tests pass, ask the user if questions arise.

- [x] 16. Add `nlp_worker/` service files
  - Create `nlp_worker/requirements.txt` with:
    - `sentence-transformers>=2.7`
    - `qdrant-client>=1.9`
    - `langdetect>=1.0.9`
    - `nltk>=3.8`
    - `numpy>=1.26`
    - Plus Celery, Django, mysqlclient (same as `ml_worker/requirements.txt`)
  - Create `nlp_worker/Dockerfile` following `ml_worker/Dockerfile` pattern:
    - Base: `python:3.11-slim`
    - Install system deps (gcc, libmysqlclient-dev)
    - Install `nlp_worker/requirements.txt` and `backend/requirements.txt`
    - Download and bake in `paraphrase-multilingual-MiniLM-L12-v2` model at build time using a `RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')"` step
    - Verify model SHA256 checksum in the same `RUN` layer
    - Set `ENV SENTENCE_TRANSFORMERS_HOME=/app/nlp_worker/models`
    - `CMD ["celery", "-A", "config", "worker", "--loglevel=info", "--concurrency=2", "-Q", "nlp"]`
  - _Requirements: 12.1, 12.3, 12.4_

- [x] 17. Update `docker-compose.yml` with `nlp-worker` and `qdrant` services
  - Add `qdrant` service:
    - Image: `qdrant/qdrant:v1.9.0`
    - Expose port `6333` internally only (no `ports:` mapping to host)
    - Add named volume `qdrant_data:/qdrant/storage`
  - Add `nlp-worker` service following `ml-worker` pattern:
    - `build.context: .`, `build.dockerfile: nlp_worker/Dockerfile`
    - `depends_on`: `db` (healthy), `redis` (healthy), `qdrant`
    - `env_file: .env`
    - `volumes`: `./nlp_worker:/app/nlp_worker`
    - `healthcheck`: `celery -A config inspect ping --timeout 5`
  - Add `qdrant_data` to top-level `volumes:`
  - _Requirements: 12.1, 12.2, 12.3, 12.5_

- [x] 18. Write property test for NLP flags contributing to FraudRiskScore
  - **Property 7: NLP flags contribute to FraudRiskScore (non-decreasing)**
  - **Validates: Requirements 9.2, 9.3**
  - In `backend/tests/test_nlp_score_property.py`:
    - Create a tender with a known spec text
    - Record `score_before` from `FraudRiskScore`
    - Run `analyze_spec_task` synchronously (mock Qdrant to return high similarity)
    - Record `score_after`
    - Assert `score_after >= score_before`
  - Use `hypothesis` with `st.integers(min_value=0, max_value=99)` for initial score values
  - _Requirements: 9.2, 9.3_

- [ ] 19. Final checkpoint — ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

---

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at key integration points
- Property tests validate universal correctness properties using `hypothesis` (already present in `backend/.hypothesis/`)
- Unit tests validate specific examples and boundary conditions
- The `nlp_worker/` directory is a new top-level service alongside `ml_worker/`; it shares the same Redis broker and MySQL database
- Qdrant is internal-only — never exposed outside the Docker Compose network
 