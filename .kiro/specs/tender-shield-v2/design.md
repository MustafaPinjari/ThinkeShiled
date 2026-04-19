# Design Document: TenderShield V2 — Enhancement Spec

## Overview

TenderShield V2 is a major evolution of the existing procurement fraud detection platform. V1 established a solid foundation: Django + Next.js, rule-based detection, Isolation Forest + Random Forest scoring, SHAP explanations, and a collusion graph. V2 addresses the critical gaps identified in the architectural review: undergraduate-level ML, no demand-side fraud detection, no investigation workflow, no feedback loop, and a CRUD dashboard that doesn't support how auditors actually work.

The goal is to transform TenderShield from a fraud *scoring* tool into a fraud *investigation intelligence platform*.

---

## Current State (V1)

| Layer | Technology | Limitation |
|---|---|---|
| Backend | Django 4.2, DRF | Solid, extend in place |
| Frontend | Next.js 16, TypeScript, Tailwind, HeroUI | Table-centric, no investigation UX |
| Database | MySQL 8 | Graph queries will not scale |
| Cache/Broker | Redis 7 (dual-purpose) | Single point of failure |
| Task Queue | Celery | No durable queuing |
| ML | Isolation Forest + Random Forest | Static, no temporal/graph learning |
| Graph | NetworkX + vis-network on MySQL adjacency tables | Decorative, not analytical |
| Explainability | SHAP | Gameable, not auditor-friendly |

---

## V2 Architecture

### Backend Services

```
┌─────────────────────────────────────────────────────────────┐
│                        API Gateway                          │
│                   (Django REST Framework)                   │
└──────────┬──────────────────────────────────────┬──────────┘
           │                                      │
    ┌──────▼──────┐                      ┌────────▼────────┐
    │  MySQL 8    │                      │    Neo4j 5      │
    │  (primary)  │                      │  (graph data)   │
    │  + replicas │                      │                 │
    └─────────────┘                      └─────────────────┘
           │
    ┌──────▼──────┐    ┌─────────────┐    ┌──────────────┐
    │   Redis 7   │    │  RabbitMQ   │    │Elasticsearch │
    │(cache + JWT)│    │(task queue) │    │(tender search)│
    └─────────────┘    └──────┬──────┘    └──────────────┘
                              │
                    ┌─────────▼─────────┐
                    │   Celery Workers  │
                    │  (ML, NLP, GNN,   │
                    │   briefs, alerts) │
                    └───────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │     Qdrant        │
                    │  (vector DB for   │
                    │  fraud DNA + NLP) │
                    └───────────────────┘
```

### New Django Apps

| App | Purpose |
|---|---|
| `cases` | Investigation case management (Case, CaseNote, CaseEvidence) |
| `labels` | Auditor feedback loop (TenderLabel, active learning queue) |
| `officers` | Procurement officer risk profiling (OfficerProfile) |
| `briefs` | LLM-generated investigation briefs (InvestigationBrief) |
| `nlp` | Tender specification NLP analysis (embeddings, similarity) |

### Extended Existing Apps

| App | Extension |
|---|---|
| `tenders` | Split tender detection, spec embedding storage |
| `detection` | SPEC_TAILORING, SPLIT_TENDER, OFFICER_* red flag types |
| `scoring` | GNN collusion probability, counterfactual explanations |
| `graph` | Neo4j integration, temporal graph queries |

---

## Feature Design

### F1: NLP Tender Specification Analysis

**Model:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

**Pipeline:**
1. On tender ingestion, extract specification text
2. Compute 384-dim embedding via sentence-transformer
3. Store embedding in Qdrant collection `tender_specs`
4. Query top-5 nearest neighbors from confirmed-fraudulent corpus
5. If cosine similarity > 0.85 to any confirmed-fraudulent spec → raise `SPEC_TAILORING` red flag
6. Also flag if similarity > 0.92 to any spec from the same buyer (copy-paste detection)

**New model field:** `Tender.spec_embedding` (stored as JSON, indexed in Qdrant)
**New red flag type:** `SPEC_TAILORING` (severity: HIGH)

---

### F2: Split Tender Detection

**Logic:** After each tender ingestion, run a Celery task that:
1. Groups tenders by `(buyer_id, category, 90-day rolling window)`
2. Sums `estimated_value` within each group
3. If sum exceeds configurable `SPLIT_TENDER_THRESHOLD` (default: 500,000) → raise `SPLIT_TENDER` red flag on all tenders in the group

**New red flag type:** `SPLIT_TENDER` (severity: HIGH)
**Config:** `SplitTenderConfig` model (threshold, window_days, per-category overrides)

---

### F3: Investigation Case Management

**Models:**
```python
Case(tender, company, status, priority, assigned_to, created_by, created_at)
CaseNote(case, author, content, created_at)
CaseEvidence(case, file, description, uploaded_by, uploaded_at)
CaseAssignment(case, assigned_to, assigned_by, assigned_at)
```

**Status flow:** `OPEN → UNDER_REVIEW → ESCALATED → CLOSED`

**Frontend:** Kanban board at `/cases` with drag-and-drop status columns. Case detail page with timeline, notes, evidence attachments, and "Export Investigation Report" (PDF).

---

### F4: Auditor Feedback Loop

**Model:**
```python
TenderLabel(tender, label_type, labeled_by, labeled_at, notes)
# label_type: CONFIRMED_FRAUD | FALSE_POSITIVE | UNDER_INVESTIGATION
```

**Active learning queue:** Celery beat task surfaces the 20 tenders with highest model uncertainty (predictions closest to 0.5) for auditor labeling each day.

**Retraining:** When labeled examples exceed 50, trigger incremental retraining of Random Forest with labeled data weighted 5x over synthetic data.

**Poisoning defense:** Labels from a single auditor that deviate >3σ from peer consensus are flagged for review before inclusion in training.

---

### F5: Procurement Officer Risk Profiling

**Model:**
```python
OfficerProfile(
    buyer,
    single_source_rate,        # % of tenders with single-source justification
    avg_deadline_days,         # average days from publication to deadline
    vendor_concentration_index, # Herfindahl index of award distribution
    repeat_award_rate,         # % of awards to same vendor in 12 months
    risk_score,
    last_computed_at
)
```

**New red flags:** `OFFICER_VENDOR_CONCENTRATION` (HHI > 0.7), `OFFICER_SHORT_DEADLINE_PATTERN` (avg < 5 days)

---

### AI1: Graph Neural Network for Collusion Detection

**Framework:** PyTorch Geometric

**Model:** `TemporalGraphSAGE`
- Nodes: companies (features: bid count, win rate, category vector, age)
- Edges: co-bid relationships (features: co-bid count, time delta, value similarity)
- Time encoding: sinusoidal position encoding on edge timestamps
- Output: per-node collusion probability [0, 1]

**Training:** Historical co-bidding patterns with `TenderLabel.CONFIRMED_FRAUD` as ground truth. Retrain weekly via Celery beat.

**Integration:** GNN collusion probability replaces/augments the existing Random Forest collusion score in the composite risk score.

---

### AI2: Adversarial Robustness Monitor

**Method:** FGSM (Fast Gradient Sign Method) adapted for tabular data

**Weekly Celery beat task:**
1. Sample 1,000 recent tenders
2. Apply FGSM perturbations to numeric features
3. Measure score change — if perturbed score drops >30 points, flag as "evasion-vulnerable"
4. Generate `VulnerabilityReport` with specific feature combinations

**Output:** Admin dashboard widget showing current evasion vulnerability score (0–100).

---

### AI3: LLM-Powered Investigation Brief Generator

**Framework:** LangChain

**Trigger:** Tender risk score ≥ 80 (configurable)

**Agent tools:**
- `get_tender_detail` — full tender data
- `get_company_profiles` — all bidder profiles
- `get_related_tenders` — same buyer/category/period
- `get_collusion_ring` — Neo4j subgraph query
- `get_legal_provisions` — relevant procurement law sections

**Output model:**
```python
InvestigationBrief(
    tender,
    summary_text,       # 2-sentence "why suspicious"
    evidence_narrative, # structured evidence list
    legal_references,   # relevant law sections
    recommended_actions,
    generated_at,
    pdf_path
)
```

---

### AI4: Counterfactual Explanations (DiCE)

**Library:** `dice-ml`

**Integration:** Run alongside SHAP in the explanation pipeline (async, low-priority Celery task).

**Output:** For each flagged tender, 3 diverse counterfactuals: "This tender would NOT be flagged if [feature] were [value]."

**Storage:** `CounterfactualExplanation` model linked to tender score.

---

### UX1: Intelligence Command Center

**Route:** `/dashboard` (replace existing)

**Three-panel layout:**
- Left (30%): Priority queue — AI-ranked "investigate today" list with urgency chip (URGENT / HIGH / ROUTINE) and one-line reasoning
- Center (40%): Geographic heatmap (Leaflet.js) — fraud risk by region/ministry, color-coded by risk level
- Right (30%): Live feed — real-time stream of new high-risk events (WebSocket or SSE)

---

### UX2: Investigation Narrative View

**Route:** `/tenders/[id]` (replace existing detail page)

**Sections:**
1. Hero: "Why this tender is suspicious" (2 sentences from LLM brief or rule summary)
2. Evidence timeline: chronological suspicious events
3. Network context: mini collusion graph (relevant subgraph only, max 50 nodes)
4. Comparable tenders: nearest confirmed fraud cases from Fraud DNA
5. Counterfactual panel: DiCE explanations in plain language
6. Action bar: Open Case | Request Review | Mark Clean | Export Brief (PDF)

---

### UX3: Temporal Graph Explorer

**Route:** `/graph` (replace existing)

**Features:**
- Time slider: scrub through months, watch edges form/dissolve
- Play/pause animation of relationship evolution
- Community detection overlay: Louvain clusters highlighted
- Click cluster → investigation brief for that collusion ring
- Node size = risk score; edge thickness = co-bid frequency

**Backend:** Neo4j temporal queries; paginated subgraph API (max 500 nodes per response)

---

### UX4: Mobile-First Field Investigator PWA

**Route:** `/mobile` (separate simplified layout)

**Features:**
- PWA with service worker (offline-capable)
- QR code scanner → company lookup
- Voice memo attachment to cases
- Push notifications for high-priority alerts
- Simplified case view (status + notes only)

---

### ARCH1: Neo4j Integration

**Migration strategy:**
1. Add Neo4j alongside MySQL (dual-write during transition)
2. Migrate `GraphNode`, `GraphEdge`, `CollusionRing` to Neo4j
3. Replace SQL graph queries with Cypher
4. Use Neo4j Graph Data Science library for Louvain community detection and PageRank

---

### ARCH2: RabbitMQ for Durable Task Queuing

**Celery broker:** Switch from Redis to RabbitMQ
**Redis:** Cache and JWT blacklist only
**Dead letter queue:** Failed tasks → DLQ with admin alert after 3 retries

---

### ARCH3: MySQL Read Replicas

**Write path:** Primary MySQL for all writes
**Read path:** Read replica for dashboard queries, company profiles, audit log
**Connection pooling:** PgBouncer-equivalent (ProxySQL for MySQL)

---

### ARCH4: Kafka Event Streaming

**Topics:**
- `tender.ingested` → fraud engine, NLP worker, split-tender detector
- `bid.ingested` → scoring worker, graph updater
- `score.computed` → alert system, brief generator trigger
- `flag.raised` → audit logger, case auto-creation (for HIGH severity)

---

### Innovation: Fraud DNA Fingerprinting

**Encoding:** Multi-modal embedding per tender:
- Numeric features (32-dim PCA of existing feature vector)
- Graph topology features (32-dim node2vec embedding from Neo4j)
- NLP specification embedding (384-dim from sentence-transformer, reduced to 64-dim via UMAP)

**Total:** 128-dim Fraud DNA vector stored in Qdrant collection `fraud_dna`

**At ingestion:** Retrieve top-5 nearest confirmed fraud cases. Surface as "Similar confirmed fraud cases" on investigation narrative view.

---

## Data Models Summary

### New Models

| Model | App | Purpose |
|---|---|---|
| `Case` | cases | Investigation case |
| `CaseNote` | cases | Case note/comment |
| `CaseEvidence` | cases | Attached evidence file |
| `CaseAssignment` | cases | Case assignment history |
| `TenderLabel` | labels | Auditor fraud/FP label |
| `ActiveLearningQueue` | labels | Uncertain predictions for labeling |
| `OfficerProfile` | officers | Procurement officer risk metrics |
| `InvestigationBrief` | briefs | LLM-generated brief |
| `CounterfactualExplanation` | scoring | DiCE counterfactuals |
| `VulnerabilityReport` | scoring | Adversarial robustness report |
| `SplitTenderConfig` | tenders | Split tender detection config |
| `SplitTenderGroup` | tenders | Grouped tenders for split detection |

### Extended Models

| Model | Extension |
|---|---|
| `Tender` | `spec_embedding`, `fraud_dna_vector`, `investigation_brief` FK |
| `RedFlag` | New types: `SPEC_TAILORING`, `SPLIT_TENDER`, `OFFICER_VENDOR_CONCENTRATION`, `OFFICER_SHORT_DEADLINE_PATTERN` |
| `TenderScore` | `gnn_collusion_score`, `counterfactual_id` FK |
| `Buyer` | `officer_profile` FK |

---

## Testing Strategy

- **Property-based tests (Hypothesis):** Fraud scoring invariants, split tender aggregation logic, officer risk metric bounds, GNN score range [0,1]
- **Unit tests:** All new model methods, Celery task logic, NLP similarity thresholds
- **Integration tests:** Case management API, feedback loop retraining trigger, Neo4j graph queries
- **Adversarial tests:** FGSM perturbation pipeline, rule poisoning detection

---

## Implementation Phases

| Phase | Scope | Priority |
|---|---|---|
| 1 | F2 (Split Tender), F3 (Cases), F4 (Feedback Loop) | Critical — no ML dependency |
| 2 | F1 (NLP), F5 (Officer Profiling), AI4 (DiCE) | High — extends existing pipeline |
| 3 | AI1 (GNN), AI3 (LLM Briefs), Fraud DNA | High — new ML infrastructure |
| 4 | UX1–UX4 redesign | High — depends on Phase 1–3 APIs |
| 5 | ARCH1–ARCH4, AI2 (Adversarial Monitor) | Medium — infrastructure hardening |
