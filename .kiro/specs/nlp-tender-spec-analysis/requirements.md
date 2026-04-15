# Requirements Document

## Introduction

NLP Tender Specification Analysis extends TenderShield with demand-side procurement fraud detection by
analyzing the *text* of tender specifications. The current pipeline detects bid-rigging and collusion
through numeric and categorical bid data; this feature adds a parallel NLP pipeline that embeds
specification text using a multilingual sentence-transformer model and applies four complementary
detectors: specification tailoring, copy-paste fraud, vague scope detection, and unusual restriction
detection. Each detector raises a dedicated `RedFlag` type, contributes to the existing
`FraudRiskScore`, and provides sentence-level explainability by highlighting the specific clauses that
triggered each flag.

---

## Glossary

- **NLP_Pipeline**: The Celery-based analysis pipeline that embeds tender specification text and runs the four NLP detectors.
- **NLP_Worker**: The `nlp-worker` Celery service that executes the NLP_Pipeline tasks.
- **Spec_Embedder**: The component that wraps the `paraphrase-multilingual-MiniLM-L12-v2` sentence-transformer model and produces 384-dimensional L2-normalized embedding vectors.
- **Vector_Store**: The thin wrapper around the Qdrant client that stores and retrieves spec embeddings.
- **Tailoring_Detector**: The NLP detector that identifies specification tailoring by comparing a tender's embedding against the fraud corpus.
- **Copy_Paste_Detector**: The NLP detector that identifies near-verbatim reuse of previously flagged or confirmed-fraud tender specifications.
- **Vague_Scope_Detector**: The NLP detector that identifies intentionally vague specifications using text statistics relative to contract value.
- **Unusual_Restriction_Detector**: The NLP detector that identifies statistically anomalous clauses by comparing sentence-level embeddings against a category-specific baseline.
- **NLP_Flag_Writer**: The component that translates `DetectionResult` objects into `RedFlag` and `SpecClauseHighlight` database records.
- **Clause_Highlighter**: The component that produces sentence-level highlights explaining why a flag was raised.
- **SpecAnalysisResult**: The database model that stores the output of one NLP analysis run for a tender.
- **SpecClauseHighlight**: The database model that stores sentence-level evidence for each NLP red flag.
- **Fraud_Corpus**: The set of Qdrant-indexed tender embeddings marked as `is_fraud_corpus=True` or `confirmed_fraud=True`.
- **Vagueness_Score**: A float in [0.0, 1.0] computed from word count, type-token ratio, Shannon entropy, and value-normalized length; higher values indicate vaguer specifications.
- **Cosine_Similarity**: The dot product of two L2-normalized vectors, yielding a float in [-1.0, 1.0].
- **RedFlag**: An existing TenderShield model representing a detected fraud indicator for a tender.
- **FraudRiskScore**: The existing 0–100 integer score aggregating all fraud signals for a tender.
- **Risk_Scorer**: The existing component that computes and persists the FraudRiskScore.
- **Qdrant**: The vector database service used to store and search spec embeddings.

---

## Requirements

---

### Requirement 1: Tender Specification Text Storage

**User Story:** As a system administrator, I want to store the full text of tender specifications alongside existing tender data, so that the NLP pipeline has the raw material it needs to detect specification-level fraud.

#### Acceptance Criteria

1. THE TenderShield SHALL accept a `spec_text` field on the tender ingestion API endpoint, with a maximum length of 100,000 characters.
2. IF a `spec_text` value exceeding 100,000 characters is submitted, THEN THE TenderShield SHALL reject the request with an HTTP 422 response and a `VALIDATION_ERROR` code.
3. THE TenderShield SHALL store `spec_text` as a plain-text field on the `Tender` model; the field SHALL be optional and default to an empty string for tenders ingested without specification text.
4. WHEN a tender with non-empty `spec_text` is ingested, THE NLP_Worker SHALL auto-detect the specification language using `langdetect` and store the detected ISO 639-1 language code in the `spec_language` field of the `Tender` record.
5. WHEN a tender's `spec_text` is updated via a PATCH request, THE TenderShield SHALL re-enqueue the NLP analysis task for that tender.

---

### Requirement 2: NLP Analysis Pipeline Execution

**User Story:** As a fraud analyst, I want NLP analysis to run automatically after every tender ingestion, so that specification-level fraud signals are available without manual intervention.

#### Acceptance Criteria

1. WHEN a tender is ingested via the API, THE TenderShield SHALL enqueue an `analyze_spec_task` Celery task for that tender immediately after the tender record is persisted.
2. WHEN `analyze_spec_task` executes for a tender with empty `spec_text`, THE NLP_Pipeline SHALL insert a `SpecAnalysisResult` record with `error="empty_spec"` and SHALL raise no NLP `RedFlag` records for that tender.
3. WHEN `analyze_spec_task` executes for a tender with non-empty `spec_text`, THE NLP_Pipeline SHALL run all four detectors (Tailoring_Detector, Copy_Paste_Detector, Vague_Scope_Detector, Unusual_Restriction_Detector) and persist a `SpecAnalysisResult` record containing per-detector scores and the list of raised flag types.
4. THE NLP_Pipeline SHALL upsert the tender's embedding vector into the Vector_Store (Qdrant) before running the vector-based detectors.
5. WHEN `analyze_spec_task` completes and at least one NLP `RedFlag` has been raised, THE NLP_Pipeline SHALL trigger recomputation of the `FraudRiskScore` for that tender.
6. THE NLP_Pipeline SHALL record the analysis duration in milliseconds in the `SpecAnalysisResult.analysis_duration_ms` field.

---

### Requirement 3: Specification Embedding

**User Story:** As a system architect, I want tender specifications to be embedded into dense vectors using a multilingual model, so that semantic similarity comparisons are language-agnostic and numerically well-defined.

#### Acceptance Criteria

1. THE Spec_Embedder SHALL use the `paraphrase-multilingual-MiniLM-L12-v2` model to produce 384-dimensional `float32` embedding vectors.
2. FOR ALL non-empty spec texts, THE Spec_Embedder SHALL produce an L2-normalized output vector such that `|norm(vector) - 1.0| < 1e-5`.
3. WHEN the same spec text is embedded twice, THE Spec_Embedder SHALL produce identical output vectors (deterministic inference).
4. WHEN an empty string is provided as input, THE Spec_Embedder SHALL return a zero vector of shape `(384,)` and SHALL NOT raise an exception.
5. THE Spec_Embedder SHALL load the model from a local cache at worker startup and SHALL NOT perform any network requests during inference.
6. THE Spec_Embedder SHALL support sentence-level embedding via `embed_sentences`, splitting the input text into sentences and returning a list of `(sentence_text, vector)` tuples.

---

### Requirement 4: Specification Tailoring Detection

**User Story:** As a fraud analyst, I want the system to detect when a tender specification has been written to match a known-fraudulent spec, so that tailored specifications designed to exclude all but one vendor are flagged for review.

#### Acceptance Criteria

1. WHEN the Tailoring_Detector computes a maximum cosine similarity of `>= 0.85` between a tender's embedding and any entry in the Fraud_Corpus, THE Tailoring_Detector SHALL return a `DetectionResult` with `flag_type=SPEC_TAILORING` and `severity=HIGH`.
2. WHEN the maximum cosine similarity between a tender's embedding and all Fraud_Corpus entries is `< 0.85`, THE Tailoring_Detector SHALL return `None` and no `SPEC_TAILORING` flag SHALL be raised for that tender.
3. WHEN a `SPEC_TAILORING` flag is raised, THE NLP_Flag_Writer SHALL store the matched tender ID and similarity score in the `SpecAnalysisResult.tailoring_similarity` and `SpecAnalysisResult.tailoring_matched_tender_id` fields.
4. WHEN a `SPEC_TAILORING` flag is raised, THE Clause_Highlighter SHALL identify the top 3 sentences most similar to the matched fraud corpus entry and store them as `SpecClauseHighlight` records linked to the `SPEC_TAILORING` `RedFlag`.

---

### Requirement 5: Copy-Paste Fraud Detection

**User Story:** As a fraud analyst, I want the system to detect near-verbatim reuse of previously flagged tender specifications, so that copy-paste fraud across procurement cycles is identified.

#### Acceptance Criteria

1. WHEN the Copy_Paste_Detector computes a maximum cosine similarity of `>= 0.92` between a tender's embedding and any entry in the Fraud_Corpus (including both `is_fraud_corpus=True` and `confirmed_fraud=True` entries), THE Copy_Paste_Detector SHALL return a `DetectionResult` with `flag_type=SPEC_COPY_PASTE` and `severity=HIGH`.
2. WHEN the maximum cosine similarity between a tender's embedding and all Fraud_Corpus entries is `< 0.92`, THE Copy_Paste_Detector SHALL return `None` and no `SPEC_COPY_PASTE` flag SHALL be raised for that tender.
3. WHEN a `SPEC_COPY_PASTE` flag is raised, THE NLP_Flag_Writer SHALL store the matched tender ID and similarity score in the `SpecAnalysisResult.copy_paste_similarity` and `SpecAnalysisResult.copy_paste_matched_tender_id` fields.
4. FOR ALL `SpecAnalysisResult` records where `flags_raised` contains `SPEC_COPY_PASTE`, THE NLP_Pipeline SHALL ensure `copy_paste_similarity >= 0.92`.
5. FOR ALL `SpecAnalysisResult` records where `flags_raised` does NOT contain `SPEC_COPY_PASTE`, THE NLP_Pipeline SHALL ensure `copy_paste_similarity` is `None` or `< 0.92`.

---

### Requirement 6: Vague Scope Detection

**User Story:** As a fraud analyst, I want the system to detect intentionally vague tender specifications, so that specs designed to enable post-award scope creep are flagged for review.

#### Acceptance Criteria

1. THE Vague_Scope_Detector SHALL compute a `vagueness_score` in the range `[0.0, 1.0]` from the following text statistics: word count, type-token ratio, Shannon entropy of word distribution, and value-normalized length (word count divided by estimated contract value in units of 100,000 INR).
2. WHEN the computed `vagueness_score` exceeds the 95th-percentile baseline for the tender's category, THE Vague_Scope_Detector SHALL return a `DetectionResult` with `flag_type=SPEC_VAGUE_SCOPE` and `severity=MEDIUM`.
3. WHEN no category baseline exists, THE Vague_Scope_Detector SHALL use a default threshold of `0.70`.
4. FOR ALL pairs of spec texts with the same `estimated_value` and `category`, IF `word_count(s1) < word_count(s2)` AND `entropy(s1) <= entropy(s2)`, THEN `vagueness_score(s1) >= vagueness_score(s2)` (monotonicity invariant).
5. WHEN a `SPEC_VAGUE_SCOPE` flag is raised, THE NLP_Flag_Writer SHALL store the vagueness score, word count, type-token ratio, entropy, value-normalized length, and category baseline in the `DetectionResult.trigger_data` and in `SpecAnalysisResult.vagueness_score`.

---

### Requirement 7: Unusual Restriction Detection

**User Story:** As a fraud analyst, I want the system to detect statistically anomalous clauses in tender specifications, so that brand-specific requirements, narrow geographic restrictions, and non-standard certifications are flagged.

#### Acceptance Criteria

1. THE Unusual_Restriction_Detector SHALL operate at the sentence level, computing the cosine distance of each sentence embedding from the category-specific centroid vector.
2. WHEN one or more sentences in a tender specification have a distance from the category centroid exceeding the category's 95th-percentile threshold, THE Unusual_Restriction_Detector SHALL return a `DetectionResult` with `flag_type=SPEC_UNUSUAL_RESTRICTION` and `severity=MEDIUM`.
3. WHEN a `SPEC_UNUSUAL_RESTRICTION` flag is raised, THE Clause_Highlighter SHALL store the anomalous sentences as `SpecClauseHighlight` records ranked by descending distance from the category centroid, linked to the `SPEC_UNUSUAL_RESTRICTION` `RedFlag`.
4. WHEN a `SPEC_UNUSUAL_RESTRICTION` flag is raised, THE NLP_Flag_Writer SHALL store the overall anomaly score in `SpecAnalysisResult.unusual_restriction_score`.

---

### Requirement 8: Sentence-Level Explainability

**User Story:** As a fraud analyst, I want to see which specific sentences in a tender specification triggered each NLP flag, so that I can quickly assess the evidence and present it to oversight bodies.

#### Acceptance Criteria

1. WHEN any NLP `RedFlag` (`SPEC_TAILORING`, `SPEC_COPY_PASTE`, `SPEC_VAGUE_SCOPE`, or `SPEC_UNUSUAL_RESTRICTION`) is raised for a tender, THE NLP_Flag_Writer SHALL create at least one `SpecClauseHighlight` record linked to that `RedFlag`.
2. THE TenderShield SHALL store each `SpecClauseHighlight` with the following fields: `sentence_text` (the verbatim sentence), `sentence_index` (0-based position in `spec_text`), `relevance_score` (float in `[0.0, 1.0]`), and `reason` (human-readable explanation of up to 500 characters).
3. THE TenderShield SHALL order `SpecClauseHighlight` records by descending `relevance_score` when retrieved for a given `RedFlag`.
4. FOR ALL `SpecClauseHighlight` records, THE TenderShield SHALL ensure `relevance_score` is in the range `[0.0, 1.0]`.

---

### Requirement 9: NLP Flag Integration with Risk Scoring

**User Story:** As a procurement auditor, I want NLP-detected fraud signals to contribute to the overall Fraud Risk Score, so that specification-level fraud is reflected in the triage priority of a tender.

#### Acceptance Criteria

1. THE TenderShield SHALL register the four new flag types (`SPEC_TAILORING`, `SPEC_COPY_PASTE`, `SPEC_VAGUE_SCOPE`, `SPEC_UNUSUAL_RESTRICTION`) as valid `FlagType` choices in the `detection` app.
2. WHEN NLP `RedFlag` records are written for a tender, THE Risk_Scorer SHALL include them in the `FraudRiskScore` computation using the existing severity-weighted formula (HIGH = 25 points, MEDIUM = 10 points, capped at 50 from flags).
3. FOR ALL tenders where at least one NLP `RedFlag` is raised, THE Risk_Scorer SHALL produce a `FraudRiskScore` after NLP analysis that is `>=` the score computed before NLP analysis.
4. THE NLP_Flag_Writer SHALL clear all previously active NLP `RedFlag` records for a tender before writing new ones, ensuring re-analysis does not accumulate duplicate flags.

---

### Requirement 10: Vector Store Management

**User Story:** As a system administrator, I want tender embeddings to be stored and searchable in a vector database, so that similarity-based detectors can operate efficiently at scale.

#### Acceptance Criteria

1. THE Vector_Store SHALL use a Qdrant collection named `tender_specs` with cosine distance as the similarity metric.
2. THE Vector_Store SHALL store the following payload fields per embedding point: `tender_id`, `category`, `is_fraud_corpus`, `confirmed_fraud`, and `ingested_at`.
3. THE Vector_Store SHALL create the `tender_specs` collection automatically on first use if it does not already exist.
4. WHEN `VectorStore.mark_fraud_corpus()` is called, THE Vector_Store SHALL update the `is_fraud_corpus` and `confirmed_fraud` payload fields for the specified tender's embedding point.
5. THE TenderShield SHALL restrict the `mark_fraud_corpus` API endpoint (`POST /api/v1/tenders/{id}/mark-fraud-corpus/`) to users with the `ADMIN` role.

---

### Requirement 11: Error Handling and Graceful Degradation

**User Story:** As a system operator, I want the NLP pipeline to degrade gracefully when dependencies are unavailable, so that partial failures do not block the rest of the fraud detection pipeline.

#### Acceptance Criteria

1. WHEN the Qdrant service is unreachable during `analyze_spec_task` execution, THE NLP_Pipeline SHALL log the error, set `SpecAnalysisResult.error="qdrant_unavailable"`, skip the vector-based detectors (Tailoring_Detector, Copy_Paste_Detector, Unusual_Restriction_Detector), and still execute the Vague_Scope_Detector.
2. WHEN a single detector raises an unhandled exception, THE NLP_Pipeline SHALL log the exception, record the error in `SpecAnalysisResult.error`, and continue executing the remaining detectors without interruption.
3. WHEN `analyze_spec_task` fails due to Qdrant unavailability, THE NLP_Worker SHALL retry the task up to 3 times using exponential backoff before marking the task as permanently failed.
4. WHEN all retry attempts are exhausted, THE NLP_Worker SHALL write an entry to the existing `AuditLog` recording the tender ID, task name, and failure reason.
5. IF `spec_text` is empty or `None` at analysis time, THEN THE NLP_Pipeline SHALL insert a `SpecAnalysisResult` with `error="empty_spec"` and SHALL NOT raise any `SPEC_*` `RedFlag` records for that tender.

---

### Requirement 12: NLP Worker Deployment

**User Story:** As a DevOps engineer, I want the NLP worker to run as an isolated service in the Docker Compose stack, so that CPU-bound NLP inference does not contend with the existing ML worker.

#### Acceptance Criteria

1. THE TenderShield SHALL provide a `nlp-worker` service in `docker-compose.yml` that runs as a separate Celery worker sharing the existing Redis broker and MySQL database.
2. THE TenderShield SHALL provide a `qdrant` service in `docker-compose.yml` exposing port 6333, accessible only within the Docker Compose network.
3. THE `nlp-worker` service SHALL run with `--concurrency=2` to limit CPU contention.
4. THE TenderShield SHALL bake the `paraphrase-multilingual-MiniLM-L12-v2` model into the `nlp-worker` Docker image at build time, verifying the model's SHA256 checksum, so that no network requests are made during inference.
5. THE `qdrant` service SHALL NOT be exposed outside the Docker Compose network; only the `nlp-worker` and `backend` services SHALL be able to reach it on port 6333.
