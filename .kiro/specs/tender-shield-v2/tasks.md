# Tasks: TenderShield V2

## Phase 1 — Backend: Core New Features (No ML Dependency)

### 1. Split Tender Detection (F2)

- [ ] 1.1 Add `SplitTenderConfig` model (threshold, window_days, per-category overrides) and migration
- [ ] 1.2 Add `SplitTenderGroup` model linking related tenders and migration
- [ ] 1.3 Add `SPLIT_TENDER` red flag type to the `RedFlag` choices
- [ ] 1.4 Implement `detect_split_tenders(tender_id)` Celery task: group by `(buyer_id, category, 90-day window)`, sum `estimated_value`, raise flag when threshold exceeded
- [ ] 1.5 Wire task to fire after each tender ingestion (post-save signal or Kafka consumer)
- [ ] 1.6 Add `GET /api/v1/tenders/split-groups/` endpoint returning grouped split-tender sets
- [ ] 1.7 Write unit tests for split tender grouping logic (boundary values: exactly at threshold, one below, one above)
- [ ] 1.8 Write property-based test: for any set of tenders from the same buyer+category within the window whose values sum > threshold, `SPLIT_TENDER` flag must be raised on all members — **Validates: F2**

### 2. Investigation Case Management (F3)

- [ ] 2.1 Create `cases` Django app
- [ ] 2.2 Implement `Case` model (tender FK, company FK nullable, status, priority, assigned_to, created_by, created_at, updated_at) and migration
- [ ] 2.3 Implement `CaseNote` model (case FK, author FK, content, created_at) and migration
- [ ] 2.4 Implement `CaseEvidence` model (case FK, file, description, uploaded_by, uploaded_at) and migration
- [ ] 2.5 Implement `CaseAssignment` model (case FK, assigned_to FK, assigned_by FK, assigned_at) and migration
- [ ] 2.6 Implement case status state machine: `OPEN → UNDER_REVIEW → ESCALATED → CLOSED` (reject invalid transitions)
- [ ] 2.7 Add REST endpoints: `POST /cases/`, `GET /cases/`, `GET /cases/{id}/`, `PATCH /cases/{id}/`, `DELETE /cases/{id}/`
- [ ] 2.8 Add nested endpoints: `POST /cases/{id}/notes/`, `POST /cases/{id}/evidence/`, `POST /cases/{id}/assign/`
- [ ] 2.9 Add `POST /cases/{id}/export/` endpoint that queues a Celery task to generate a PDF investigation report
- [ ] 2.10 Implement PDF report generation task (ReportLab or WeasyPrint): case summary, notes timeline, evidence list, red flags
- [ ] 2.11 Write unit tests for case status transitions (valid and invalid)
- [ ] 2.12 Write property-based test: case status can only move forward in the defined flow, never backward — **Validates: F3**

### 3. Auditor Feedback Loop (F4)

- [ ] 3.1 Create `labels` Django app
- [ ] 3.2 Implement `TenderLabel` model (tender FK, label_type: CONFIRMED_FRAUD|FALSE_POSITIVE|UNDER_INVESTIGATION, labeled_by FK, labeled_at, notes) and migration
- [ ] 3.3 Implement `ActiveLearningQueue` model (tender FK, uncertainty_score, surfaced_at, labeled_at nullable) and migration
- [ ] 3.4 Add REST endpoints: `POST /tenders/{id}/label/`, `GET /tenders/{id}/label/`, `GET /labels/queue/` (active learning queue)
- [ ] 3.5 Implement Celery beat task `populate_active_learning_queue`: daily, surfaces 20 tenders with model uncertainty closest to 0.5
- [ ] 3.6 Implement label poisoning guard: flag labels from a single auditor that deviate >3σ from peer consensus before including in training
- [ ] 3.7 Implement retraining trigger: when labeled examples exceed 50, enqueue `retrain_with_labels` Celery task
- [ ] 3.8 Extend ML retraining pipeline to weight labeled examples 5x over synthetic data
- [ ] 3.9 Write unit tests for poisoning guard (consensus deviation detection)
- [ ] 3.10 Write property-based test: uncertainty score for any tender must be in [0.0, 1.0] and tenders closest to 0.5 are always surfaced first — **Validates: F4**

### 4. Procurement Officer Risk Profiling (F5)

- [ ] 4.1 Create `officers` Django app
- [ ] 4.2 Implement `OfficerProfile` model (buyer FK one-to-one, single_source_rate, avg_deadline_days, vendor_concentration_index, repeat_award_rate, risk_score, last_computed_at) and migration
- [ ] 4.3 Implement `compute_officer_profile(buyer_id)` function: calculate all four metrics from tender/bid history
- [ ] 4.4 Implement Celery task to recompute officer profiles after each tender award
- [ ] 4.5 Add `OFFICER_VENDOR_CONCENTRATION` red flag (HHI > 0.7) to detection engine
- [ ] 4.6 Add `OFFICER_SHORT_DEADLINE_PATTERN` red flag (avg deadline < 5 days over last 20 tenders) to detection engine
- [ ] 4.7 Add REST endpoints: `GET /officers/`, `GET /officers/{buyer_id}/`, `GET /officers/{buyer_id}/red-flags/`
- [ ] 4.8 Write unit tests for HHI calculation and deadline pattern detection
- [ ] 4.9 Write property-based test: vendor_concentration_index (HHI) must always be in [0.0, 1.0]; single-vendor monopoly must always yield 1.0 — **Validates: F5**

---

## Phase 2 — Backend: NLP & Enhanced Scoring

### 5. NLP Tender Specification Analysis (F1)

- [ ] 5.1 Add `sentence-transformers` and `qdrant-client` to `requirements.txt`
- [ ] 5.2 Add `spec_embedding` JSON field to `Tender` model and migration
- [ ] 5.3 Create Qdrant collection `tender_specs` on startup (idempotent)
- [ ] 5.4 Implement `compute_spec_embedding(tender_id)` Celery task: load model, compute 384-dim embedding, store in `Tender.spec_embedding` and upsert to Qdrant
- [ ] 5.5 Implement `detect_spec_tailoring(tender_id)` function: query Qdrant top-5 neighbors from confirmed-fraudulent corpus; raise `SPEC_TAILORING` if cosine similarity > 0.85
- [ ] 5.6 Implement copy-paste detection: query same-buyer specs; raise `SPEC_TAILORING` if similarity > 0.92 to any prior spec from same buyer
- [ ] 5.7 Add `SPEC_TAILORING` red flag type to detection engine
- [ ] 5.8 Wire `compute_spec_embedding` and `detect_spec_tailoring` to tender ingestion pipeline
- [ ] 5.9 Add `GET /tenders/{id}/spec-similarity/` endpoint returning top-5 similar tenders with similarity scores
- [ ] 5.10 Write unit tests for similarity threshold logic (mock embeddings)
- [ ] 5.11 Write property-based test: cosine similarity between any two identical spec texts must equal 1.0; similarity between any two specs must be in [-1.0, 1.0] — **Validates: F1**

### 6. Counterfactual Explanations via DiCE (AI4)

- [ ] 6.1 Add `dice-ml` to `requirements.txt`
- [ ] 6.2 Implement `CounterfactualExplanation` model (tender FK, counterfactuals JSON, generated_at) and migration
- [ ] 6.3 Implement `generate_counterfactuals(tender_id)` Celery task (low-priority queue): run DiCE against the Random Forest model, generate 3 diverse counterfactuals
- [ ] 6.4 Wire task to fire asynchronously after scoring (does not block score response)
- [ ] 6.5 Add `GET /tenders/{id}/counterfactuals/` endpoint
- [ ] 6.6 Write unit tests for counterfactual generation (verify output structure and feature bounds)

### 7. Async SHAP Computation

- [ ] 7.1 Move SHAP computation out of the scoring critical path into a low-priority Celery task
- [ ] 7.2 Add `shap_status` field to `TenderScore` (PENDING | READY) and migration
- [ ] 7.3 Update `GET /tenders/{id}/explanation/` to return `shap_status: "pending"` with 202 if SHAP not yet computed
- [ ] 7.4 Write unit test verifying score endpoint returns immediately without waiting for SHAP

---

## Phase 3 — ML/AI: Advanced Models

### 8. Graph Neural Network for Collusion Detection (AI1)

- [ ] 8.1 Add `torch`, `torch-geometric` to `ml_worker/requirements.txt`
- [ ] 8.2 Implement `TemporalGraphSAGE` model class: node features (bid count, win rate, category vector, company age), edge features (co-bid count, time delta, value similarity), sinusoidal time encoding
- [ ] 8.3 Implement graph dataset builder: extract co-bidding graph from MySQL/Neo4j, encode as PyG `Data` object with temporal edge attributes
- [ ] 8.4 Implement training script `train_gnn.py`: train on historical co-bidding with `TenderLabel.CONFIRMED_FRAUD` as ground truth, save model checkpoint
- [ ] 8.5 Implement `score_gnn_collusion(company_ids)` inference function: load checkpoint, return per-node collusion probability [0, 1]
- [ ] 8.6 Add `gnn_collusion_score` field to `TenderScore` model and migration
- [ ] 8.7 Integrate GNN score into composite risk score (weighted average with existing RF score)
- [ ] 8.8 Add Celery beat task for weekly GNN retraining
- [ ] 8.9 Write unit tests for GNN output range and graph dataset builder
- [ ] 8.10 Write property-based test: GNN collusion score for any company must be in [0.0, 1.0]; composite risk score must remain in [0, 100] after GNN integration — **Validates: AI1**

### 9. Adversarial Robustness Monitor (AI2)

- [ ] 9.1 Implement `generate_adversarial_examples(n_samples)` function: FGSM adapted for tabular data, perturb numeric features within realistic bounds
- [ ] 9.2 Implement `VulnerabilityReport` model (generated_at, evasion_rate, vulnerable_features JSON, sample_count) and migration
- [ ] 9.3 Implement `run_adversarial_audit()` Celery beat task (weekly): sample 1,000 recent tenders, apply FGSM, measure score drop, generate report
- [ ] 9.4 Add `GET /admin/vulnerability-reports/` endpoint (ADMIN only)
- [ ] 9.5 Write unit tests for FGSM perturbation bounds (perturbed features must stay within realistic domain)

### 10. LLM-Powered Investigation Brief Generator (AI3)

- [ ] 10.1 Add `langchain`, `langchain-openai` (or `langchain-anthropic`), `reportlab` to `requirements.txt`
- [ ] 10.2 Implement `InvestigationBrief` model (tender FK, summary_text, evidence_narrative JSON, legal_references JSON, recommended_actions JSON, generated_at, pdf_path) and migration
- [ ] 10.3 Implement LangChain agent tools: `get_tender_detail`, `get_company_profiles`, `get_related_tenders`, `get_collusion_ring`, `get_legal_provisions`
- [ ] 10.4 Implement `generate_investigation_brief(tender_id)` Celery task: run LangChain agent with structured brief template, store result in `InvestigationBrief`
- [ ] 10.5 Implement PDF generation from `InvestigationBrief` (ReportLab): 1-page formatted report
- [ ] 10.6 Wire trigger: enqueue brief generation when tender score ≥ 80 (configurable via env var)
- [ ] 10.7 Add `GET /tenders/{id}/brief/` endpoint (returns brief JSON + PDF download URL)
- [ ] 10.8 Add `POST /tenders/{id}/brief/regenerate/` endpoint (ADMIN only, re-queues generation)
- [ ] 10.9 Write unit tests for brief trigger threshold logic and PDF generation

### 11. Fraud DNA Fingerprinting (Innovation)

- [ ] 11.1 Add `umap-learn`, `node2vec` to `ml_worker/requirements.txt`
- [ ] 11.2 Implement `compute_fraud_dna(tender_id)` function: concatenate 32-dim PCA of numeric features + 32-dim node2vec graph embedding + 64-dim UMAP-reduced spec embedding = 128-dim vector
- [ ] 11.3 Create Qdrant collection `fraud_dna` on startup (idempotent)
- [ ] 11.4 Implement Celery task to compute and upsert Fraud DNA vector after scoring completes
- [ ] 11.5 Implement `find_similar_fraud_cases(tender_id, top_k=5)` function: query Qdrant, return nearest confirmed fraud cases with similarity scores
- [ ] 11.6 Add `GET /tenders/{id}/similar-cases/` endpoint
- [ ] 11.7 Add `fraud_dna_vector` JSON field to `Tender` model and migration
- [ ] 11.8 Write unit tests for DNA vector dimensionality (must always be 128-dim)

---

## Phase 4 — Infrastructure

### 12. Neo4j Graph Database Integration (ARCH1)

- [ ] 12.1 Add `neo4j` Python driver to `requirements.txt`; add Neo4j service to `docker-compose.yml`
- [ ] 12.2 Implement `Neo4jClient` singleton with connection pooling and health check
- [ ] 12.3 Implement Cypher query layer: `create_company_node`, `create_bid_edge`, `find_collusion_rings`, `get_company_subgraph`
- [ ] 12.4 Implement dual-write: on `GraphNode`/`GraphEdge` save, write to both MySQL and Neo4j
- [ ] 12.5 Implement `migrate_graph_to_neo4j` management command: bulk-migrate existing adjacency table data
- [ ] 12.6 Replace `detect_collusion_rings()` SQL query with Cypher connected-components query
- [ ] 12.7 Add Neo4j Graph Data Science Louvain community detection call for cluster identification
- [ ] 12.8 Add `GET /graph/communities/` endpoint returning Louvain clusters
- [ ] 12.9 Write integration tests for Neo4j graph queries (requires Neo4j test instance)

### 13. RabbitMQ Durable Task Queue (ARCH2)

- [ ] 13.1 Add `kombu[rabbitmq]` to `requirements.txt`; add RabbitMQ service to `docker-compose.yml`
- [ ] 13.2 Update Celery broker URL to RabbitMQ; keep Redis for result backend and cache
- [ ] 13.3 Configure dead letter queue (DLQ) for failed tasks with 3-retry policy
- [ ] 13.4 Add Celery beat task to alert admins when DLQ depth exceeds threshold
- [ ] 13.5 Update `.env.example` with `RABBITMQ_URL` variable
- [ ] 13.6 Write integration test: verify task survives broker restart (durable queue)

### 14. MySQL Read Replicas & Connection Pooling (ARCH3)

- [ ] 14.1 Add `DATABASE_READ_URL` to Django settings and `.env.example`
- [ ] 14.2 Implement Django database router: route `SELECT` queries for dashboard/reporting apps to read replica
- [ ] 14.3 Add ProxySQL service to `docker-compose.yml` for connection pooling
- [ ] 14.4 Add read-only database user with `SELECT`-only grants (migration script)
- [ ] 14.5 Write unit test for database router (verify read queries route to replica)

### 15. Elasticsearch for Tender Search (Performance)

- [ ] 15.1 Add `elasticsearch-dsl` to `requirements.txt`; add Elasticsearch service to `docker-compose.yml`
- [ ] 15.2 Define `TenderDocument` index mapping (title, description, buyer, category, status, risk_score, created_at)
- [ ] 15.3 Implement `index_tender(tender_id)` Celery task: upsert tender to Elasticsearch on save
- [ ] 15.4 Implement `bulk_index_tenders` management command for initial indexing
- [ ] 15.5 Replace MySQL full-text search in `GET /tenders/` with Elasticsearch query
- [ ] 15.6 Write unit tests for search query builder and result mapping

### 16. Redis Caching for Dashboard Stats (Performance)

- [ ] 16.1 Implement `cache_dashboard_stats()` function: compute KPI stats and cache in Redis with 5-minute TTL
- [ ] 16.2 Invalidate cache on `score.computed` event (signal or Kafka consumer)
- [ ] 16.3 Update `GET /tenders/stats/` to serve from cache; fall back to DB on cache miss
- [ ] 16.4 Write unit test verifying cache hit/miss behavior

### 17. Materialized Views for Company Metrics (Performance)

- [ ] 17.1 Create MySQL materialized view (scheduled event or trigger) for `company_bid_metrics`: bid count, win count, win rate, avg bid value per company
- [ ] 17.2 Update `CompanyProfile` serializer to read from materialized view
- [ ] 17.3 Add management command `refresh_company_metrics` to manually trigger refresh
- [ ] 17.4 Write unit test verifying metrics match raw query results

### 18. Kafka Event Streaming (ARCH4) *

- [ ] 18.1 Add `confluent-kafka` to `requirements.txt`; add Kafka + Zookeeper services to `docker-compose.yml`
- [ ] 18.2 Define Kafka topics: `tender.ingested`, `bid.ingested`, `score.computed`, `flag.raised`
- [ ] 18.3 Implement `KafkaProducer` wrapper with schema validation
- [ ] 18.4 Replace post-save signal task enqueueing with Kafka producer calls
- [ ] 18.5 Implement Kafka consumers for: fraud engine, NLP worker, alert system, audit logger
- [ ] 18.6 Write integration test for end-to-end event flow (tender ingested → score computed)

---

## Phase 5 — Frontend

### 19. Intelligence Command Center Dashboard (UX1)

- [ ] 19.1 Replace `/dashboard` page with three-panel layout (priority queue | heatmap | live feed)
- [ ] 19.2 Implement priority queue panel: fetch from `GET /tenders/?ordering=-risk_score&status=unreviewed`, render urgency chips (URGENT/HIGH/ROUTINE) with one-line AI reasoning
- [ ] 19.3 Integrate Leaflet.js geographic heatmap: fetch region-level fraud risk from `GET /tenders/stats/by-region/`, render choropleth
- [ ] 19.4 Add `GET /tenders/stats/by-region/` backend endpoint
- [ ] 19.5 Implement live feed panel: SSE or WebSocket connection to `GET /events/stream/` for real-time high-risk events
- [ ] 19.6 Add `GET /events/stream/` SSE endpoint (Django StreamingHttpResponse)
- [ ] 19.7 Write component tests for priority queue sorting and urgency chip logic

### 20. Investigation Narrative View (UX2)

- [ ] 20.1 Replace `/tenders/[id]` detail page with narrative investigation layout
- [ ] 20.2 Implement hero section: display `InvestigationBrief.summary_text` or fallback rule-based summary
- [ ] 20.3 Implement evidence timeline component: chronological list of red flags and bid events
- [ ] 20.4 Implement mini collusion graph component: render subgraph (max 50 nodes) from `GET /graph/?center={company_id}&depth=2`
- [ ] 20.5 Implement comparable tenders panel: fetch from `GET /tenders/{id}/similar-cases/`
- [ ] 20.6 Implement counterfactual panel: fetch from `GET /tenders/{id}/counterfactuals/`, render in plain language ("Would NOT be flagged if...")
- [ ] 20.7 Implement action bar: Open Case (POST /cases/), Mark Clean (POST /tenders/{id}/label/), Export Brief (download PDF)
- [ ] 20.8 Write component tests for action bar state (disabled states, loading states)

### 21. Temporal Graph Explorer (UX3)

- [ ] 21.1 Replace `/graph` page with temporal graph explorer layout
- [ ] 21.2 Implement time slider component: date range picker that filters graph edges by timestamp
- [ ] 21.3 Implement animated graph: play/pause button that steps through time, adding/removing edges
- [ ] 21.4 Integrate Louvain community overlay: fetch from `GET /graph/communities/`, color-code clusters
- [ ] 21.5 Implement cluster drill-down: click cluster → slide-in panel with investigation brief for that ring
- [ ] 21.6 Implement graph pagination: request subgraph by center node + depth (max 500 nodes)
- [ ] 21.7 Write component tests for time slider filtering logic

### 22. Case Management Kanban UI (F3 Frontend)

- [ ] 22.1 Create `/cases` page with Kanban board: four columns (OPEN | UNDER_REVIEW | ESCALATED | CLOSED)
- [ ] 22.2 Implement drag-and-drop status update (PATCH /cases/{id}/ on drop)
- [ ] 22.3 Create `/cases/[id]` detail page: timeline of notes, evidence list, assignment history
- [ ] 22.4 Implement note editor: rich text input, POST /cases/{id}/notes/
- [ ] 22.5 Implement evidence upload: file input, POST /cases/{id}/evidence/
- [ ] 22.6 Implement "Export Investigation Report" button: trigger PDF generation, poll for completion, download
- [ ] 22.7 Write component tests for Kanban drag-and-drop state transitions

### 23. Officer Risk Profile UI (F5 Frontend)

- [ ] 23.1 Add `/officers` page: table of procurement officers sorted by risk score
- [ ] 23.2 Create `/officers/[id]` detail page: metric cards (single-source rate, avg deadline, HHI, repeat award rate), tender history, red flags
- [ ] 23.3 Add officer risk badge to tender detail page (link to officer profile)
- [ ] 23.4 Write component tests for metric card rendering

### 24. Auditor Feedback UI (F4 Frontend)

- [ ] 24.1 Add label buttons to tender detail page: "Confirm Fraud" | "False Positive" | "Under Investigation"
- [ ] 24.2 Add `/labels/queue` page: active learning queue showing uncertain tenders awaiting auditor review
- [ ] 24.3 Show label status badge on tender list and detail pages
- [ ] 24.4 Write component tests for label button state (already labeled, pending, unlabeled)

### 25. Mobile-First Field Investigator PWA (UX4) *

- [ ] 25.1 Add `next-pwa` and service worker configuration to Next.js
- [ ] 25.2 Create `/mobile` route with simplified layout (case list + company lookup only)
- [ ] 25.3 Implement QR code scanner component (`react-qr-reader`): scan company registration QR → navigate to company profile
- [ ] 25.4 Implement voice memo attachment: `MediaRecorder` API, upload to `POST /cases/{id}/evidence/`
- [ ] 25.5 Implement push notification subscription: `POST /notifications/subscribe/` with Web Push API
- [ ] 25.6 Add `POST /notifications/subscribe/` backend endpoint (VAPID keys, `pywebpush`)
- [ ] 25.7 Write PWA manifest and offline fallback page

---

## Phase 6 — Security & Observability

### 26. SHAP Output Access Control

- [ ] 26.1 Restrict `GET /tenders/{id}/explanation/` to ADMIN and AUDITOR roles only (already role-gated — verify and add test)
- [ ] 26.2 Add `shap_redacted` flag to explanation response for public-facing API contexts
- [ ] 26.3 Add audit log entry whenever SHAP explanation is accessed
- [ ] 26.4 Write unit test verifying unauthenticated requests to explanation endpoint return 401

### 27. Rule Integrity Monitoring

- [ ] 27.1 Add `RuleChangeLog` model (rule_id, changed_by, old_value JSON, new_value JSON, changed_at) and migration
- [ ] 27.2 Override `DetectionRule` save/delete signals to write to `RuleChangeLog`
- [ ] 27.3 Add `GET /admin/rule-changes/` endpoint (ADMIN only)
- [ ] 27.4 Add Celery beat task: alert admins if any rule suppresses flags for a specific vendor (vendor-targeted suppression detection)
- [ ] 27.5 Write unit test for rule change logging

### 28. JWT Blacklist Hardening

- [ ] 28.1 Add fallback: if Redis is unavailable, reject all token validation requests (fail-closed, not fail-open)
- [ ] 28.2 Add Redis health check to `/health` endpoint
- [ ] 28.3 Write unit test for fail-closed behavior on Redis unavailability

---

## Phase 7 — Property-Based Test Suite

### 29. Fraud Scoring Invariants

- [ ] 29.1 Write property-based test: composite risk score must always be in [0, 100] for any valid tender input — **Validates: scoring pipeline**
- [ ] 29.2 Write property-based test: adding more red flags to a tender must never decrease its risk score — **Validates: scoring monotonicity**
- [ ] 29.3 Write property-based test: a tender with zero bids must always have risk score ≥ 50 (SINGLE_BIDDER rule) — **Validates: rule engine**

### 30. Detection Rule Invariants

- [ ] 30.1 Write property-based test: PRICE_ANOMALY flag must fire if and only if winning bid deviates > 40% from estimate — **Validates: detection engine**
- [ ] 30.2 Write property-based test: REPEAT_WINNER flag must fire if and only if win rate > 60% in category within 12 months — **Validates: detection engine**
- [ ] 30.3 Write property-based test: SPLIT_TENDER flag must fire for all tenders in a group when group total exceeds threshold — **Validates: F2**

### 31. Officer Profile Metric Invariants

- [ ] 31.1 Write property-based test: HHI (vendor_concentration_index) must be in [0.0, 1.0] for any award distribution — **Validates: F5**
- [ ] 31.2 Write property-based test: single-vendor monopoly (100% awards to one vendor) must yield HHI = 1.0 — **Validates: F5**
- [ ] 31.3 Write property-based test: perfectly distributed awards (equal share across N vendors) must yield HHI = 1/N — **Validates: F5**

### 32. GNN Score Invariants

- [ ] 32.1 Write property-based test: GNN collusion score must be in [0.0, 1.0] for any valid company node — **Validates: AI1**
- [ ] 32.2 Write property-based test: composite risk score must remain in [0, 100] after GNN score integration — **Validates: AI1**
