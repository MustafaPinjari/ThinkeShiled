# Tasks: TenderShield

## Phase 1: Project Setup and Infrastructure

- [x] 1. Docker Compose and service scaffolding
  - [x] 1.1 Write `docker-compose.yml` defining services: `frontend` (Next.js :3000), `backend` (Django :8000), `db` (MySQL 8 :3306), `ml-worker` (Celery), `redis` (:6379)
  - [x] 1.2 Write `Dockerfile` for the Django backend (Python 3.11, install requirements, run gunicorn)
  - [x] 1.3 Write `Dockerfile` for the ML worker (Python 3.11, install ml_worker/requirements.txt, run celery worker)
  - [x] 1.4 Write `Dockerfile` for the Next.js frontend (Node 20, install deps, build, serve)
  - [x] 1.5 Add health-check directives to each service in `docker-compose.yml` (all services healthy within 60 s)
  - [x] 1.6 Create `.env.example` documenting all required environment variables (DB credentials, SECRET_KEY, JWT keys, SMTP, REDIS_URL, FRONTEND_ORIGIN)

- [x] 2. Django project bootstrap
  - [x] 2.1 Initialise Django 4.x project under `backend/` with `django-admin startproject config .`
  - [x] 2.2 Create Django apps: `authentication`, `tenders`, `bids`, `detection`, `scoring`, `xai`, `companies`, `graph`, `alerts`, `audit`
  - [x] 2.3 Configure `settings.py`: MySQL database, Redis cache/broker, installed apps, DRF, simplejwt, cors-headers, ratelimit, bcrypt password hasher (cost ≥ 12)
  - [x] 2.4 Add `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS`, and `CORS_ALLOWED_ORIGINS` settings
  - [x] 2.5 Create `backend/requirements.txt` pinning: Django, djangorestframework, djangorestframework-simplejwt, django-cors-headers, django-ratelimit, mysqlclient, celery, redis, bcrypt, bleach, shap, scikit-learn, pandas, joblib, reportlab

- [x] 3. Next.js project verification and base setup
  - [x] 3.1 Confirm Next.js app exists under `frontend/` with Tailwind CSS configured
  - [x] 3.2 Install additional frontend dependencies: `vis-network`, `d3`, `axios`, `react-query`, `date-fns`
  - [x] 3.3 Create `frontend/lib/api.ts` Axios instance with JWT interceptor (attach Bearer token, handle 401 refresh)
  - [x] 3.4 Create `frontend/contexts/AuthContext.tsx` providing login, logout, and role state
  - [x] 3.5 Create `frontend/components/Layout.tsx` with JWT guard (redirect to `/login` if unauthenticated), role-aware navigation menu, and advisory disclaimer banner


## Phase 2: Data Models and Database Migrations

- [x] 4. Core Django models
  - [x] 4.1 Create `authentication/models.py`: `User` model with `username`, `email`, `password_hash`, `role` (AUDITOR/ADMIN), `failed_login_attempts`, `locked_until`
  - [x] 4.2 Create `tenders/models.py`: `Tender` model matching OCDS-inspired schema (tender_id UK, title, category, estimated_value, currency, submission_deadline, buyer_id, buyer_name, status, timestamps)
  - [x] 4.3 Create `bids/models.py`: `Bid` model (bid_id UK, FK tender, FK bidder, bid_amount, submission_timestamp) and `Bidder` model (bidder_id UK, bidder_name, registered_address, director_names)
  - [x] 4.4 Create `detection/models.py`: `RedFlag` (FK tender, FK bidder, flag_type, severity, rule_version, trigger_data JSON, is_active, raised_at, cleared_at) and `RuleDefinition` (rule_code UK, description, severity, is_active, parameters JSON)
  - [x] 4.5 Create `scoring/models.py`: `FraudRiskScore` (FK tender, score, ml_anomaly_score, ml_collusion_score, red_flag_contribution, model_version, weight_config JSON, computed_at) — one row per computation, latest = current
  - [x] 4.6 Create `xai/models.py`: `SHAPExplanation` (FK tender, model_version, rule_engine_version, shap_values JSON, top_factors JSON, shap_failed bool, computed_at) and `MLModelVersion` (model_type, version, trained_at, feature_importances JSON, model_artifact_path, is_active)
  - [x] 4.7 Create `companies/models.py`: `CompanyProfile` (FK bidder, total_bids, total_wins, win_rate, avg_bid_deviation, active_red_flag_count, highest_fraud_risk_score, risk_status enum, collusion_ring_id FK, updated_at)
  - [x] 4.8 Create `graph/models.py`: `CollusionRing` (ring_id UK, member_bidder_ids JSON, member_count, detected_at, is_active), `GraphNode` (FK bidder, metadata JSON), `GraphEdge` (FK source_node, FK target_node, edge_type enum CO_BID/SHARED_DIRECTOR/SHARED_ADDRESS, FK tender, metadata JSON)
  - [x] 4.9 Create `alerts/models.py`: `Alert` (FK tender, FK user, alert_type, fraud_risk_score, top_red_flags JSON, delivery_status, retry_count, created_at, delivered_at) and `AlertSettings` (user FK, threshold, category, email_enabled)
  - [x] 4.10 Create `audit/models.py`: `AuditLog` (event_type, timestamp UTC, FK user, affected_entity_type, affected_entity_id, data_snapshot JSON, ip_address) — override `save()` to block updates and `delete()` to raise `PermissionDenied`
  - [x] 4.11 Generate and apply all initial Django migrations (`makemigrations` + `migrate`)
  - [x] 4.12 Write a Django management command `create_superuser_admin` for initial admin user creation (documents in setup guide)


## Phase 3: Authentication and RBAC

- [x] 5. JWT authentication service
  - [x] 5.1 Configure `djangorestframework-simplejwt` with RS256 signing, access token expiry range [15 min, 24 hr] from env var, refresh token 7 days, token blacklist app enabled
  - [x] 5.2 Implement `POST /api/v1/auth/login/` view: validate credentials, check account lock, issue JWT, return `{access, refresh, expires_in, role}`, increment `failed_login_attempts` on failure (HTTP 401)
  - [x] 5.3 Implement account lockout logic: after 5 consecutive failures within 10 minutes, set `locked_until`, send email notification via Celery task
  - [x] 5.4 Implement `POST /api/v1/auth/logout/` view: blacklist the access token in Redis
  - [x] 5.5 Implement `POST /api/v1/auth/refresh/` view: issue new access token from valid refresh token
  - [x] 5.6 Create custom DRF permission classes: `IsAdminRole` (role == ADMIN), `IsAuditorOrAdmin` (role in [AUDITOR, ADMIN])
  - [x] 5.7 Apply `django-ratelimit` to login endpoint (10 req/min per IP) and globally (100 req/min per authenticated user, HTTP 429)
  - [x] 5.8 Write unit tests for login success, login failure counter, account lockout, token refresh, and logout blacklisting


## Phase 4: Tender and Bid Data Ingestion

- [x] 6. Tender ingestion API
  - [x] 6.1 Implement `TenderSerializer` validating all OCDS-inspired fields (mandatory: tender_id, title, category, estimated_value, currency, submission_deadline, buyer_id, buyer_name)
  - [x] 6.2 Implement `POST /api/v1/tenders/` single-tender creation view (ADMIN only); write AuditLog entry on success
  - [x] 6.3 Implement `POST /api/v1/tenders/upload/` CSV batch upload view (ADMIN only): parse CSV, validate each row, reject rows with missing mandatory fields, return validation report listing rejected rows with reasons; store valid rows within 5 s; support ≥ 10,000 rows per batch within 60 s
  - [x] 6.4 Enforce duplicate `tender_id` rejection: return rejected record in validation report without overwriting existing record
  - [x] 6.5 Implement `GET /api/v1/tenders/` paginated list view with query params: `score_min`, `score_max`, `category`, `buyer_name`, `date_from`, `date_to`, `flag_type`, `ordering`, `page`, `page_size`
  - [x] 6.6 Implement `GET /api/v1/tenders/{id}/` detail view, `GET /api/v1/tenders/{id}/score/`, `GET /api/v1/tenders/{id}/explanation/`, `GET /api/v1/tenders/{id}/red-flags/`, `GET /api/v1/tenders/{id}/score-history/`
  - [x] 6.7 Write unit tests for CSV validation (valid rows, missing fields, duplicate tender_id, batch size)


- [x] 7. Bid ingestion API
  - [x] 7.1 Implement `BidSerializer` validating fields: bid_id, tender_id, bidder_id, bidder_name, bid_amount, submission_timestamp
  - [x] 7.2 Implement `POST /api/v1/bids/` single bid creation view (ADMIN only); upsert `Bidder` record; write AuditLog entry
  - [x] 7.3 Implement `POST /api/v1/bids/bulk/` bulk bid ingestion view (ADMIN only)
  - [x] 7.4 Implement `GET /api/v1/bids/?tender_id={id}` list view (AUDITOR, ADMIN)
  - [x] 7.5 After bid ingestion, enqueue Celery tasks: `evaluate_rules_task(tender_id)`, `compute_score_task(tender_id)`, `score_ml_task(tender_id)`, `update_company_profile_task(bidder_id)`, `update_graph_task(tender_id)`
  - [x] 7.6 Write unit tests for bid creation, bulk ingestion, and post-ingestion task enqueueing


## Phase 5: Rule-Based Fraud Detection Engine

- [x] 8. FraudDetectionEngine implementation
  - [x] 8.1 Implement `FraudDetectionEngine` class in `detection/engine.py` with `evaluate_rules(tender_id)`, `get_active_rules()`, and `add_rule(rule)` methods
  - [x] 8.2 Implement SINGLE_BIDDER rule: exactly 1 bidder at submission deadline → RedFlag HIGH
  - [x] 8.3 Implement PRICE_ANOMALY rule: winning bid deviates > 40% from estimated_value in either direction → RedFlag MEDIUM
  - [x] 8.4 Implement REPEAT_WINNER rule: same bidder wins > 60% of tenders in a category within rolling 12-month window → RedFlag HIGH
  - [x] 8.5 Implement SHORT_DEADLINE rule: time between publication and submission_deadline < 3 calendar days → RedFlag MEDIUM
  - [x] 8.6 Implement LINKED_ENTITIES rule: two or more bidders share registered_address or director_name → RedFlag HIGH
  - [x] 8.7 Implement COVER_BID_PATTERN rule: bidder submits bids in 3+ tenders in same category within 30 days with 0 wins → RedFlag HIGH
  - [x] 8.8 Load `RuleDefinition` records from DB at startup; refresh on each `evaluate_rules()` call (hot-reload, no restart required)
  - [x] 8.9 Ensure all rules are evaluated within 2 seconds of a tender record being stored; write AuditLog entry for each RedFlag raised/cleared
  - [x] 8.10 Implement `POST /api/v1/rules/` endpoint (ADMIN only) to add new rule definitions at runtime
  - [x] 8.11 Write unit tests for each rule at boundary values (exactly 1 bidder, exactly 40% deviation, exactly 60% win rate, exactly 3 days deadline, shared address, cover-bid threshold)


## Phase 6: ML Pipeline

- [x] 9. Feature engineering
  - [x] 9.1 Implement `compute_bid_screens(bids, tender)` in `ml_worker/services/feature_engineering.py`: compute `cv_bids`, `bid_spread_ratio`, `norm_winning_distance`, `single_bidder_flag`, `price_deviation_pct`, `deadline_days`, `repeat_winner_rate`, `bidder_count`, `winner_bid_rank`
  - [x] 9.2 Return `null` for all ML scores when bid count < 3 (per Requirement 4.5)
  - [x] 9.3 Write unit tests for each bid screen formula with known inputs and expected outputs

- [x] 10. ML model training and inference
  - [x] 10.1 Implement `train_isolation_forest(feature_df)` in `ml_worker/train.py`: fit `IsolationForest(contamination=0.05)`, normalize output to [0, 1] via min-max scaling, serialize with `joblib`
  - [x] 10.2 Implement `train_random_forest(feature_df, labels)` in `ml_worker/train.py`: fit `RandomForestClassifier(class_weight='balanced')`, serialize with `joblib`
  - [x] 10.3 Implement `score_tender(tender_id)` Celery task in `ml_worker/tasks.py`: load active models, compute feature vector, run both models, write `ml_anomaly_score` and `ml_collusion_score` to `FraudRiskScore`, insert `MLModelVersion` record
  - [x] 10.4 Implement scheduled model retraining Celery beat task: load labeled tenders, compute features, retrain both models, insert new `MLModelVersion`, deactivate previous version, log to AuditLog; minimum interval 24 hours (configurable)
  - [x] 10.5 Implement `POST /api/v1/tenders/{id}/rescore/` endpoint (ADMIN only) to trigger manual rescore
  - [x] 10.6 Write unit tests for model training, inference output range [0, 1], and retraining cycle

- [-] 11. SHAP explainability
  - [x] 11.1 Implement `compute_shap(tender_id, model_version)` in `ml_worker/services/shap_explainer.py`: use `TreeExplainer` for Random Forest, `KernelExplainer` fallback for Isolation Forest; store per-feature SHAP values in `SHAPExplanation`
  - [x] 11.2 Derive top-5 factors sorted by absolute SHAP magnitude; map to plain-language templates (e.g., "Winning bid was {pct}% below the estimated value.")
  - [x] 11.3 On SHAP exception: set `shap_failed = True`, log failure to AuditLog, fall back to red-flag-only explanation
  - [x] 11.4 Version-stamp each `SHAPExplanation` with `model_version` and `rule_engine_version`
  - [x] 11.5 Write unit tests for SHAP completeness (one value per feature), top-5 ordering, fallback behavior, and version stamping


## Phase 7: Fraud Risk Scoring

- [x] 12. RiskScorer implementation
  - [x] 12.1 Implement `RiskScorer.compute_score(tender_id, weights=None)` in `scoring/scorer.py`: aggregate HIGH flags × 25 + MEDIUM flags × 10 (capped at 50) + ml_anomaly × 30 + ml_collusion × 20; clamp result to integer [0, 100]
  - [x] 12.2 Apply custom weight overrides when an Administrator has configured them (stored in `AlertSettings` or a dedicated `ScoringWeightConfig` record)
  - [x] 12.3 Persist each computation as a new `FraudRiskScore` row with `computed_at` timestamp; write AuditLog entry
  - [x] 12.4 Trigger `compute_score` within 5 seconds of any new bid ingested or any RedFlag raised/cleared for the tender
  - [x] 12.5 Implement `RiskScorer.get_score(tender_id)` returning the latest `FraudRiskScore` row
  - [x] 12.6 Write unit tests for scoring formula at boundary values, clamping to [0, 100], custom weight application, and score persistence


## Phase 8: XAI Explainer API

- [x] 13. XAI API endpoints
  - [x] 13.1 Implement `XAIExplainer.explain(tender_id, model_version)` service method: retrieve `SHAPExplanation`, assemble top-5 plain-language factors, include all active RedFlags with rule text and trigger data
  - [x] 13.2 Implement `XAIExplainer.fallback_explain(tender_id)` for SHAP-failed tenders: return red-flag-only explanation
  - [x] 13.3 Wire `GET /api/v1/tenders/{id}/explanation/` to return explanation JSON within 3 seconds (per Requirement 6.3)
  - [x] 13.4 Write unit tests for explanation assembly, fallback path, and response latency


## Phase 9: Company Behavioral Tracking

- [x] 14. BehavioralTracker implementation
  - [x] 14.1 Implement `BehavioralTracker.update_profile(bidder_id)` Celery task: recompute `total_bids`, `total_wins`, `win_rate`, `avg_bid_deviation`, `active_red_flag_count`, `highest_fraud_risk_score`; persist to `CompanyProfile`; complete within 10 seconds of bid/award ingestion
  - [x] 14.2 Implement `flag_high_risk(bidder_id, reason)`: set `risk_status = HIGH_RISK` when win rate > 60% in a category over rolling 12 months, or when bidder is linked to a `CollusionRing`
  - [x] 14.3 Implement `GET /api/v1/companies/` paginated list and `GET /api/v1/companies/{id}/` detail views
  - [x] 14.4 Implement `GET /api/v1/companies/{id}/tenders/` and `GET /api/v1/companies/{id}/red-flags/` views
  - [x] 14.5 Ensure `CompanyProfile` history is retained for minimum 5 years (no hard-delete policy)
  - [x] 14.6 Write unit tests for metric computation correctness, HIGH_RISK status transitions, and profile update timing


## Phase 10: Collusion Network Graph

- [x] 15. CollusionGraph implementation
  - [x] 15.1 Implement `CollusionGraph.update_graph(tender_id)` Celery task: upsert `GraphNode` for each bidder; create `CO_BID` edges for all bidder pairs on the same tender; create `SHARED_DIRECTOR` and `SHARED_ADDRESS` edges from `Bidder` registry data; complete within 30 seconds of new bid/company data
  - [x] 15.2 Implement `detect_collusion_rings()`: find connected components with ≥ 3 nodes connected by HIGH-severity RedFlag edges; create `CollusionRing` records with unique identifiers; trigger `AlertSystem` with severity HIGH for each new ring
  - [x] 15.3 Implement `GET /api/v1/graph/` returning `{nodes, edges}` JSON; support `?edge_type=` filter
  - [x] 15.4 Implement `GET /api/v1/graph/rings/` and `GET /api/v1/graph/rings/{ring_id}/` views
  - [x] 15.5 Write unit tests for edge creation (CO_BID, SHARED_DIRECTOR, SHARED_ADDRESS), collusion ring detection threshold (exactly 3 nodes), and alert triggering


## Phase 11: Alerts and Notifications

- [x] 16. AlertSystem implementation
  - [x] 16.1 Implement `AlertSystem.check_and_alert(tender_id)`: compare `FraudRiskScore` against global threshold (default 70) and per-category thresholds; create `Alert` records for all AUDITOR and ADMIN users; include tender_id, title, score, top 3 RedFlags, and detail page link
  - [x] 16.2 Implement in-app notification delivery (store `Alert` records; frontend polls or uses WebSocket)
  - [x] 16.3 Implement email notification via Celery task: send within 60 seconds of threshold-crossing event when email is enabled
  - [x] 16.4 Implement `retry_failed_emails()` Celery beat task: retry up to 3 times at 5-minute intervals; log each failed attempt to AuditLog
  - [x] 16.5 Implement `GET /api/v1/alerts/` (last 90 days), `GET /api/v1/alerts/{id}/`, `POST /api/v1/alerts/settings/` (ADMIN), `GET /api/v1/alerts/settings/` endpoints
  - [x] 16.6 Write unit tests for threshold firing, per-category threshold override, alert content, retry logic, and 90-day history filter


## Phase 12: Audit Logging and Compliance Export

- [x] 17. Audit logging and PDF export
  - [x] 17.1 Implement `write_audit_log(event_type, user, entity_type, entity_id, data_snapshot, ip_address)` utility called from all event handlers: user login/logout, tender ingestion, score computation, RedFlag raised/cleared, alert sent, user-initiated status change
  - [x] 17.2 Enforce immutability: `AuditLog.save()` raises `PermissionDenied` on update; `AuditLog.delete()` raises `PermissionDenied`; MySQL user has INSERT-only on `audit_log` table
  - [x] 17.3 Implement `GET /api/v1/audit-log/` paginated list view (ADMIN only)
  - [x] 17.4 Implement `POST /api/v1/audit-log/export/` Celery task: generate PDF report of all AuditLog entries for a date range using `reportlab`; return task_id; complete within 30 seconds
  - [x] 17.5 Implement `GET /api/v1/audit-log/export/{task_id}/status/` polling endpoint returning download URL on completion
  - [x] 17.6 Ensure AuditLog entries are retained for minimum 7 years (no hard-delete policy; document in setup guide)
  - [x] 17.7 Write unit tests for log creation on each event type, immutability enforcement, and PDF export generation


## Phase 13: Frontend Pages

- [x] 18. Login page (`/login`)
  - [x] 18.1 Implement `frontend/app/login/page.tsx`: username/password form, call `POST /api/v1/auth/login/`, store JWT in `AuthContext`, redirect to `/dashboard` on success, display error message on 401

- [x] 19. Dashboard page (`/dashboard`)
  - [x] 19.1 Implement `frontend/app/dashboard/page.tsx` with SSR initial load: fetch paginated tender list sorted by Fraud_Risk_Score descending
  - [x] 19.2 Implement `frontend/components/tables/TenderTable.tsx`: paginated, sortable columns (score, deadline, category, buyer_name); color-coded score badges (green 0–39, amber 40–69, red 70–100); advisory disclaimer
  - [x] 19.3 Implement `frontend/components/ui/FilterPanel.tsx`: score range, category, buyer_name, date range, flag_type filters; update list within 1 second on filter change
  - [x] 19.4 Implement `frontend/components/ui/SummaryStats.tsx`: total tenders, count with score ≥ 70, count with active HIGH RedFlags, count of CollisionRings
  - [x] 19.5 Ensure dashboard loads initial list within 2 seconds for up to 50,000 records; verify responsive layout at 1024px–2560px

- [x] 20. Tender detail page (`/tenders/[id]`)
  - [x] 20.1 Implement `frontend/app/tenders/[id]/page.tsx`: fetch tender detail, score, explanation, red flags, bids
  - [x] 20.2 Implement `frontend/components/ui/ScoreCard.tsx`: display score with color band and advisory disclaimer
  - [x] 20.3 Implement `frontend/components/charts/SHAPChart.tsx`: D3.js horizontal bar chart of top-5 SHAP values; render within 3 seconds of page request
  - [x] 20.4 Implement `frontend/components/ui/RedFlagList.tsx`: list flag type, severity, trigger data, rule text
  - [x] 20.5 Implement `frontend/components/tables/BidTable.tsx`: all bids with bid screens displayed
  - [x] 20.6 Implement plain-language explanation section below SHAP chart

- [x] 21. Company pages (`/companies`, `/companies/[id]`)
  - [x] 21.1 Implement `frontend/app/companies/page.tsx`: paginated company profile list
  - [x] 21.2 Implement `frontend/app/companies/[id]/page.tsx`: metrics grid (win rate, avg deviation, risk status), tender timeline, associated RedFlags

- [x] 22. Collusion graph page (`/graph`)
  - [x] 22.1 Implement `frontend/app/graph/page.tsx`: fetch graph data from `GET /api/v1/graph/`
  - [x] 22.2 Implement `frontend/components/charts/GraphCanvas.tsx`: vis-network force-directed graph with zoom, pan, edge-type filter (CO_BID, SHARED_DIRECTOR, SHARED_ADDRESS), click-to-navigate to company profile
  - [x] 22.3 Implement `frontend/components/ui/CollusionRingPanel.tsx`: list detected rings with member count and detection date

- [x] 23. Alerts page (`/alerts`)
  - [x] 23.1 Implement `frontend/app/alerts/page.tsx`: alert history list (last 90 days) with tender link, score, top RedFlags
  - [x] 23.2 Implement threshold settings form (ADMIN only): global threshold, per-category overrides, email toggle

- [x] 24. Audit log page (`/audit`)
  - [x] 24.1 Implement `frontend/app/audit/page.tsx` (ADMIN only): paginated audit log table
  - [x] 24.2 Implement `frontend/components/ui/ExportPanel.tsx`: date range picker, trigger PDF export, poll for completion, download link


## Phase 14: API Security Hardening

- [x] 25. Security hardening
  - [x] 25.1 Verify JWT requirement on all endpoints except `/api/v1/auth/login/`; return HTTP 401 for missing or expired tokens
  - [x] 25.2 Verify HTTPS enforcement (`SECURE_SSL_REDIRECT = True`); HTTP requests receive HTTP 301
  - [x] 25.3 Verify rate limiting: 100 req/min per authenticated user (HTTP 429); 10 req/min per IP on login endpoint
  - [x] 25.4 Verify all user-supplied inputs are validated via DRF serializers and sanitized with `bleach`; ORM-only DB access (no raw SQL)
  - [x] 25.5 Verify CORS headers restrict access to configured `FRONTEND_ORIGIN` only
  - [x] 25.6 Verify unrecognized JWT signing key returns HTTP 401 and writes AuditLog entry
  - [x] 25.7 Write security-focused unit tests for each of the above controls


## Phase 15: Property-Based Tests (Hypothesis)

All property tests use `@settings(max_examples=100)` and are tagged with:
```python
# Feature: tender-shield, Property N: <property_text>
```

- [x] 26. Authentication property tests (`backend/tests/test_auth.py`)
  - [x] 26.1 **[PBT]** Property 1 — JWT Expiry Bounds: for any configured expiry in [900, 86400] seconds, the issued JWT `exp` claim must fall within that range from issuance. Strategy: `st.integers(min_value=900, max_value=86400)`. **Validates: Requirements 1.1**
  - [x] 26.2 **[PBT]** Property 2 — Failed Login Counter Increment: for any invalid password string, `failed_attempts` increments by exactly 1 and response is HTTP 401. Strategy: `st.text()` filtered to not match valid password. **Validates: Requirements 1.2**
  - [x] 26.3 **[PBT]** Property 3 — RBAC Enforcement: for any AUDITOR JWT, all write operations (POST/PUT/PATCH/DELETE) on protected endpoints return HTTP 403; for any ADMIN JWT, write operations do not return 403. Strategy: `st.sampled_from(['AUDITOR', 'ADMIN'])`. **Validates: Requirements 1.4**

- [x] 27. Ingestion property tests (`backend/tests/test_ingestion.py`)
  - [x] 27.1 **[PBT]** Property 4 — CSV Schema Validation: for any CSV row with all mandatory fields present and valid, the row is accepted and stored; for any row missing one or more mandatory fields, the row is rejected with a reason in the validation report. Strategy: `st.builds(TenderCSVRow, ...)` with valid/invalid variants. **Validates: Requirements 2.1, 2.2**
  - [x] 27.2 **[PBT]** Property 5 — Bid Record Acceptance: for any bid record with all required fields, the record is accepted and stored. Strategy: `st.builds(BidRecord, ...)`. **Validates: Requirements 2.4**
  - [x] 27.3 **[PBT]** Property 6 — Duplicate Tender Rejection Preserves Original: for any existing tender, submitting a new record with the same tender_id is rejected and the original record remains unchanged. Strategy: `st.builds(Tender, ...)`. **Validates: Requirements 2.5**

- [x] 28. Rule engine property tests (`backend/tests/test_rules.py`)
  - [x] 28.1 **[PBT]** Property 7 — Red Flag Rules Fire Correctly: for any tender satisfying a rule trigger condition, the corresponding RedFlag is raised with the correct type and severity; for any tender not satisfying the condition, the flag is not raised. Covers all 6 rules. Strategy: `st.builds(Tender, ...)` with trigger conditions. **Validates: Requirements 3.1, 3.2, 3.3, 3.4, 3.5, 3.6**

- [x] 29. ML pipeline property tests (`backend/tests/test_ml.py`)
  - [x] 29.1 **[PBT]** Property 8 — Bid Screens Computed for Sufficient Bids: for any tender with ≥ 3 bids, all three bid screens (cv_bids, bid_spread_ratio, norm_winning_distance) are non-null; for any tender with < 3 bids, ML scores are null. Strategy: `st.lists(st.floats(min_value=0.01), min_size=0)` with size branching. **Validates: Requirements 4.1, 4.5**
  - [x] 29.2 **[PBT]** Property 9 — ML Model Outputs Bounded in [0, 1]: for any valid 9-feature vector, Isolation Forest anomaly score and Random Forest collusion probability are both in [0.0, 1.0]. Strategy: `st.lists(st.floats(min_value=0.0, max_value=1e6, allow_nan=False), min_size=9, max_size=9)`. **Validates: Requirements 4.2, 4.3**

- [x] 30. Scoring property tests (`backend/tests/test_scoring.py`)
  - [x] 30.1 **[PBT]** Property 10 — Fraud Risk Score Formula and Bounds: for any combination of active RedFlag severities and ML scores, the computed score equals the weighted aggregate formula clamped to [0, 100]; custom weight overrides replace defaults when configured. Strategy: `st.builds(ScoringInputs, high_flags=st.integers(0,10), medium_flags=st.integers(0,10), ml_anomaly=st.floats(0,1), ml_collusion=st.floats(0,1))`. **Validates: Requirements 5.1, 5.2, 5.6**

- [x] 31. XAI property tests (`backend/tests/test_xai.py`)
  - [x] 31.1 **[PBT]** Property 11 — SHAP Explanation Completeness: for any tender with ML scores, the SHAP explanation contains a value for every feature in the feature vector, top-5 factors are present and sorted by absolute SHAP magnitude, and all active RedFlags appear in the explanation. Strategy: `st.builds(Tender, ...)` with ML scores. **Validates: Requirements 6.1, 6.2, 6.4**
  - [x] 31.2 **[PBT]** Property 12 — Explanation Version Stamps: for any generated explanation, `model_version` and `rule_engine_version` are non-null and match the currently active versions. Strategy: `st.builds(Explanation, ...)`. **Validates: Requirements 6.5**

- [x] 32. Behavioral tracking property tests (`backend/tests/test_behavioral.py`)
  - [x] 32.1 **[PBT]** Property 13 — Company Profile Metrics Correctness: for any set of bid and award records for a bidder, the computed profile metrics match the values derived by applying the metric formulas to the underlying records. Strategy: `st.lists(st.builds(BidRecord, ...))`. **Validates: Requirements 7.2**
  - [x] 32.2 **[PBT]** Property 14 — HIGH_RISK Status Invariant: for any bidder whose win rate in a single category exceeds 60% over 12 months, or who is linked to a CollusionRing, `risk_status` is HIGH_RISK; a bidder not meeting either condition must not have HIGH_RISK set by these rules. Strategy: `st.builds(CompanyHistory, win_rate=st.floats(0,1), in_ring=st.booleans())`. **Validates: Requirements 7.3, 7.4**

- [x] 33. Graph property tests (`backend/tests/test_graph.py`)
  - [x] 33.1 **[PBT]** Property 15 — Collusion Graph Edge Invariants: for any two bidders co-bidding on the same tender, a CO_BID edge exists; for any two bidders sharing a director name, a SHARED_DIRECTOR edge exists; for any two bidders sharing a registered address, a SHARED_ADDRESS edge exists. Strategy: `st.lists(st.builds(Bidder, ...))`. **Validates: Requirements 8.1, 8.2, 8.3**
  - [x] 33.2 **[PBT]** Property 16 — Collusion Ring Detection: for any connected component with ≥ 3 bidder nodes on HIGH-severity RedFlag edges, a CollusionRing is created with a unique identifier and an Alert with severity HIGH is triggered. Strategy: `st.builds(GraphComponent, size=st.integers(2, 10))`. **Validates: Requirements 8.4, 8.7**

- [x] 34. Alert property tests (`backend/tests/test_alerts.py`)
  - [x] 34.1 **[PBT]** Property 17 — Alert Threshold Firing: for any tender whose score reaches or exceeds the configured threshold (global or per-category), Alert records are created for all AUDITOR and ADMIN users, each containing tender_id, title, score, top 3 RedFlags, and a detail page link. Strategy: `st.integers(min_value=0, max_value=100)` for scores, `st.integers(min_value=0, max_value=100)` for thresholds. **Validates: Requirements 10.1, 10.3, 10.6**

- [x] 35. Audit log property tests (`backend/tests/test_audit.py`)
  - [x] 35.1 **[PBT]** Property 18 — Audit Log Completeness and Immutability: for any event of the specified types, an AuditLog entry is created with all required fields; for any existing AuditLog entry, any attempt to update or delete it raises PermissionDenied. Strategy: `st.builds(AuditEvent, event_type=st.sampled_from(EVENT_TYPES))`. **Validates: Requirements 11.1, 11.2, 11.3**

- [x] 36. Security property tests (`backend/tests/test_security.py`)
  - [x] 36.1 **[PBT]** Property 19 — JWT Required for Protected Endpoints: for any protected endpoint (all except `/api/v1/auth/login/`), a request without a valid JWT receives HTTP 401. Strategy: `st.sampled_from(PROTECTED_ENDPOINTS)`. **Validates: Requirements 12.1**
  - [x] 36.2 **[PBT]** Property 20 — Input Sanitization: for any user-supplied input containing SQL injection or XSS payloads, the stored value is sanitized such that no injection is executed and no script content is stored verbatim. Strategy: `st.text()` combined with injection payload list. **Validates: Requirements 12.4**


## Phase 16: Integration Tests and CI/CD

- [x] 37. Integration tests
  - [x] 37.1 Write integration test for full bid ingestion → rule evaluation → score recomputation → alert pipeline (against test Docker Compose stack)
  - [x] 37.2 Write integration test for ML model retraining cycle: ingest labeled tenders, trigger retraining, verify new `MLModelVersion` record and updated scores
  - [x] 37.3 Write integration test for PDF audit export generation: create audit events, trigger export, verify PDF download
  - [x] 37.4 Write integration test for email notification delivery with mock SMTP (verify retry logic on failure)

  - [x] 37.5 Write integration test for graph update after bid ingestion: verify CO_BID edges and collusion ring detection

- [x] 38. Frontend tests
  - [x] 38.1 Write Jest + React Testing Library unit tests for `ScoreCard`, `RedFlagList`, `SHAPChart`, `FilterPanel`, and `TenderTable` components
  - [x] 38.2 Write Playwright end-to-end tests for: login flow, dashboard filtering, tender detail page (SHAP chart renders, advisory disclaimer present), graph page rendering
  - [x] 38.3 Verify advisory disclaimer is present on all pages displaying a `Fraud_Risk_Score`

- [x] 39. CI/CD pipeline
  - [x] 39.1 Create `.github/workflows/ci.yml`: on push to `main`, run Django tests (`pytest`), run frontend tests (`jest --ci`), build Docker images for all services
  - [x] 39.2 Add Docker image build steps for `backend`, `ml-worker`, and `frontend` services; tag images with commit SHA
  - [x] 39.3 Add health-check step in CI: start Docker Compose stack, wait for all services healthy within 60 seconds, run smoke tests against `/health` endpoint
  - [x] 39.4 Document zero-downtime deployment strategy in `docs/deployment.md`: run migrations before routing traffic to new backend container

- [x] 40. Setup guide and health endpoint
  - [x] 40.1 Implement `GET /health` endpoint: return HTTP 200 `{status: "ok", db: "ok", redis: "ok", ml_worker: "ok"}` when all services reachable; HTTP 503 `{status: "degraded", ...}` when any service is unreachable
  - [x] 40.2 Write `docs/setup.md` documenting: environment variable configuration, database migration steps, initial admin user creation, ML model training invocation, and PDF export setup
  - [x] 40.3 Write `docs/deployment.md` documenting: Docker Compose startup, zero-downtime deployment procedure, CI/CD pipeline overview

