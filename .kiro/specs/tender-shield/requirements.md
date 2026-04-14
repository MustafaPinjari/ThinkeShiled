# Requirements Document

## Introduction

TenderShield is an AI-powered government tender fraud detection platform designed to identify bid-rigging,
collusion, price-fixing, and other procurement fraud patterns in e-procurement systems such as India's
Government e-Marketplace (GeM). The platform combines a rule-based engine with machine learning models,
explainable AI (XAI), a 0–100 fraud risk scoring system, behavioral company profiling, and a collusion
network graph to give procurement auditors and oversight bodies actionable, evidence-backed intelligence.

---

## External Research Foundation

The requirements below are grounded in the following external references. These are cited as justification
for design decisions and are NOT generated system features.

### Research Papers

| # | Paper | Key Contribution | Relevance |
|---|-------|-----------------|-----------|
| R1 | Imhof, Karagök & Rutz (2021). *Detecting bid-rigging coalitions in different countries and auction formats.* arXiv:2105.00337 | Coalition-based ML screens using bid distribution statistics to flag cartels | Justifies the hybrid rule + ML approach and the use of bid-spread screens |
| R2 | Wachs et al. (2020). *Anomaly Detection in Public Procurements using the Open Contracting Data Standard.* ResearchGate | Isolation Forest + Decision Tree on OCDS data to detect anomalous tenders | Justifies Isolation Forest as an unsupervised anomaly detector and OCDS schema adoption |
| R3 | Arxiv:2304.10105 (2023). *Automatic Procurement Fraud Detection with Machine Learning.* | 9-feature neural network representation per procurement event; multi-class fraud type classification | Justifies feature engineering approach and multi-label fraud classification |
| R4 | Springer (2024). *A machine learning approach to detect collusion in public procurement with limited information.* DOI:10.1007/s42001-024-00293-4 | Leverages only outcome data (winner, price) with theoretical bidding behavior models | Justifies detection even when full bid data is unavailable |
| R5 | Springer (2022). *A Machine Learning Approach for Flagging Incomplete Bid-Rigging Cartels.* DOI:10.1007/s10614-022-10315-w | Combines bid-distribution screens with ML to detect partial cartels | Justifies statistical screens (CV of bids, bid-spread ratio) as features |
| R6 | EPJ Data Science (2025). *Detection of fraud in public procurement using data-driven methods: a systematic mapping study.* | ML models dominate collusion detection; statistical analysis dominates favoritism detection | Justifies the hybrid rule-based + ML architecture |
| R7 | Arxiv:2410.07091 (2024). *Collusion Detection with Graph Neural Networks.* | GNN-based collusion detection across national markets | Justifies the collusion network graph feature |
| R8 | Arxiv:2512.16037 (2024). *Explainable AI in Big Data Fraud Detection.* | SHAP and LIME for interpretable fraud decisions at scale | Justifies XAI requirement using SHAP value attribution |
| R9 | ResearchGate (2021). *Network Analysis for Fraud Detection in Portuguese Public Procurement.* | Graph-oriented DB + rules engine for procurement entity relationships | Justifies graph-based company relationship mapping |
| R10 | Arxiv:2512.19491 (2024). *A machine learning and network science approach to detecting fraud and corruption in Mexico.* | Combined contract-level features + network patterns outperform either alone | Justifies combining ML scores with network centrality metrics |

### Government Report Analysis

| # | Source | Finding | Design Impact |
|---|--------|---------|---------------|
| G1 | GeM Portal (gem.gov.in) — mandatory since 2020 | Lowest-bid-wins policy incentivizes quality fraud and vendor concentration | Requires price anomaly detection relative to market benchmarks |
| G2 | Gujarat Samachar (2025). *GeM portal faces corruption allegations* | Goods listed above market price; unofficial dealings for product listing | Requires price-vs-market-benchmark comparison as a fraud indicator |
| G3 | Chemistry World (2025). *India reforms GeM procurement system* | Substandard supplies delivered; no quality verification; vendor gaming | Requires repeat-winner and vendor-concentration tracking |
| G4 | OECD Foreign Bribery Report (2014) — cited by World Bank (2020) | Over 50% of foreign bribery cases involve public procurement contracts | Validates the problem scope and urgency |
| G5 | World Bank ProACT Platform (2024) | Procurement data from 46 countries used for risk scoring | Justifies multi-indicator risk scoring approach |
| G6 | World Bank Red Flags System — North Macedonia | Suspicious pattern identification in procurement data for collusion/manipulation | Justifies rule-based red-flag engine as a first-pass filter |
| G7 | NDTV (2025). *Tamil Nadu Rs 1,020 crore case* | Contracts awarded to pre-decided contractors; 7.5–10% bribe for construction projects | Validates bid-rotation and pre-decided winner detection requirements |
| G8 | Times of India (2025). *Rs 65 crore Mithi desilting scam* | BMC officials, contractors, middlemen colluded across 13 entities | Validates multi-entity collusion network detection |

### Open Datasets

| # | Dataset | Schema Basis | Usage |
|---|---------|-------------|-------|
| D1 | Open Contracting Data Standard (OCDS) — open-contracting.org | Tender, Award, Contract, Buyer, Supplier entities | Primary schema for TenderShield data model |
| D2 | World Bank ProACT — 46-country procurement data | Contract value, winner, bidder count, duration | Feature engineering reference |
| D3 | Cardinal (open-contracting.org, 2024) — open-source red-flag library | Collusion risk indicators requiring individual bid values | Reference implementation for statistical screens |
| D4 | Simulated GeM-inspired dataset | Tender ID, category, estimated value, bid prices, winner, company registration | Training data schema for ML models |

### Related Existing Projects

| # | Project | Features | Limitations | TenderShield Advantage |
|---|---------|----------|-------------|----------------------|
| P1 | World Bank ProACT | Multi-country risk scoring, data aggregation | No real-time alerts, no XAI, no graph visualization | Real-time alerts + SHAP explanations + network graph |
| P2 | Cardinal (Open Contracting Partnership) | Open-source red-flag indicators on OCDS data | CLI tool only, no dashboard, no ML scoring | Full web dashboard + ML hybrid scoring |
| P3 | World Bank Red Flags System (North Macedonia) | Rule-based suspicious pattern detection | Static rules, no behavioral tracking | Dynamic ML + behavioral company profiles |
| P4 | CompraNet Graph Analysis (Mexico) | Network analysis of procurement collusion | Research prototype, not production-ready | Production-ready Django + Next.js stack |

### News / Article Insights — Real Fraud Patterns

| # | Case | Fraud Pattern | Detection Signal |
|---|------|--------------|-----------------|
| N1 | Tamil Nadu Rs 1,020 crore construction scam (NDTV, 2025) | Pre-decided winner; contracts fudged before tender opening | Single bidder tenders; winner known before deadline |
| N2 | Mumbai ICU bed fake tender fraud — Rs 6 crore (Free Press Journal, 2025) | Forged government resolution; fake tender documents | Document authenticity anomaly; unregistered vendor |
| N3 | Mithi river desilting scam — Rs 65 crore (Times of India, 2025) | 13-entity collusion ring; bribes as flight tickets/hotel stays | Shared directors/addresses across bidding companies |
| N4 | GeM price inflation (Gujarat Samachar, 2025) | Products listed above market price; unofficial listing fees | Price deviation > threshold from market benchmark |
| N5 | GeM substandard supplies (Chemistry World, 2025) | Same vendor wins repeatedly; quality not verified | Repeat-winner concentration index |

### Additional Insights — Legal and Deployment Constraints

| # | Constraint | Impact on Design |
|---|-----------|-----------------|
| L1 | Indian Competition Act 2002 — Section 3 prohibits bid-rigging | Fraud scores must be advisory only; human review required before legal action |
| L2 | Personal Data Protection Bill (India) — company data privacy | Company profiles must store only publicly available procurement data |
| L3 | Right to Information Act (India) | Audit logs must be exportable for RTI compliance |
| L4 | EU AI Act (2026) — high-risk AI transparency obligation | SHAP-based explanations satisfy explainability requirements for high-risk AI |
| L5 | Deployment barrier — limited internet in rural procurement offices | Offline-capable export (PDF reports) required alongside web dashboard |

---

## Glossary

- **TenderShield**: The AI-powered fraud detection platform described in this document.
- **Fraud_Detection_Engine**: The hybrid rule-based and ML component that analyzes tender data and produces fraud signals.
- **Risk_Scorer**: The component that aggregates fraud signals into a 0–100 Fraud Risk Score.
- **XAI_Explainer**: The component that generates human-readable explanations for each fraud score using SHAP values.
- **Behavioral_Tracker**: The component that maintains longitudinal company-level intelligence across tenders.
- **Collusion_Graph**: The interactive network visualization showing relationships between companies, shared directors, and co-bidding patterns.
- **Alert_System**: The component that notifies designated users when a tender's Fraud Risk Score exceeds a configured threshold.
- **Tender**: A government procurement event with defined scope, estimated value, deadline, and bidder submissions.
- **Bidder**: A company or entity that submits a bid in response to a Tender.
- **Fraud_Risk_Score**: An integer in the range [0, 100] representing the probability-weighted fraud risk of a Tender or Bidder.
- **Red_Flag**: A rule-based indicator that a specific fraud pattern has been detected in a Tender or Bidder record.
- **Bid_Screen**: A statistical measure derived from the distribution of bids in a Tender (e.g., coefficient of variation, bid-spread ratio) used as an ML feature (per R1, R5).
- **OCDS**: Open Contracting Data Standard — the schema used for structuring procurement data (per D1).
- **SHAP**: SHapley Additive exPlanations — the XAI method used to attribute fraud score contributions to individual features (per R8).
- **Collusion_Ring**: A group of Bidders detected as coordinating bids across multiple Tenders.
- **Audit_Log**: An immutable, timestamped record of all system actions, score changes, and user decisions.
- **JWT**: JSON Web Token — the authentication mechanism used to secure API endpoints.
- **Dashboard**: The Next.js web interface through which users interact with TenderShield.

---

## Requirements

---

### Requirement 1: User Authentication and Access Control

**User Story:** As a procurement auditor, I want to securely log in and access only the data relevant to my role, so that sensitive fraud intelligence is protected from unauthorized access.

#### Acceptance Criteria

1. WHEN a user submits valid credentials, THE TenderShield SHALL issue a signed JWT with a configurable expiry of no less than 15 minutes and no more than 24 hours.
2. WHEN a user submits invalid credentials, THE TenderShield SHALL return an HTTP 401 response and increment a failed-attempt counter for that account.
3. WHEN a user account accumulates 5 consecutive failed login attempts within a 10-minute window, THE TenderShield SHALL lock the account and send an email notification to the registered address.
4. WHILE a JWT is valid, THE TenderShield SHALL enforce role-based access control, granting read-only access to Auditor role and read-write access to Administrator role.
5. WHEN a JWT expires, THE TenderShield SHALL reject subsequent API requests with an HTTP 401 response until the user re-authenticates.
6. THE TenderShield SHALL store all passwords as bcrypt hashes with a minimum cost factor of 12.

---

### Requirement 2: Tender Data Ingestion

**User Story:** As a system administrator, I want to ingest tender data from CSV uploads and REST API sources, so that TenderShield has current procurement records to analyze.

#### Acceptance Criteria

1. THE TenderShield SHALL accept tender data uploads in CSV format conforming to the OCDS-inspired schema defined in the Data Model (fields: tender_id, title, category, estimated_value, currency, submission_deadline, buyer_id, buyer_name).
2. WHEN a CSV file is uploaded, THE TenderShield SHALL validate each row against the schema and reject rows with missing mandatory fields, returning a validation report listing each rejected row and the reason.
3. WHEN a valid tender record is ingested, THE TenderShield SHALL store it in the database within 5 seconds of upload completion.
4. THE TenderShield SHALL accept bid records linked to a Tender via a REST API endpoint, with fields: bid_id, tender_id, bidder_id, bidder_name, bid_amount, submission_timestamp.
5. IF a duplicate tender_id is detected during ingestion, THEN THE TenderShield SHALL reject the duplicate record and include it in the validation report without overwriting the existing record.
6. THE TenderShield SHALL support ingestion of a minimum of 10,000 tender records per batch upload without exceeding a processing time of 60 seconds.

---

### Requirement 3: Rule-Based Red Flag Detection

**User Story:** As a fraud analyst, I want the system to automatically flag tenders that match known fraud patterns, so that I can prioritize my manual review queue.

*Justified by: G6 (World Bank Red Flags System), R6 (hybrid rule + ML architecture), N1–N5 (real fraud patterns).*

#### Acceptance Criteria

1. WHEN a Tender has exactly one Bidder at submission deadline, THE Fraud_Detection_Engine SHALL raise a Red_Flag of type SINGLE_BIDDER with severity HIGH.
2. WHEN the winning bid amount deviates from the Tender's estimated_value by more than 40% in either direction, THE Fraud_Detection_Engine SHALL raise a Red_Flag of type PRICE_ANOMALY with severity MEDIUM.
3. WHEN the same Bidder wins more than 60% of Tenders in a given category within a rolling 12-month window, THE Fraud_Detection_Engine SHALL raise a Red_Flag of type REPEAT_WINNER with severity HIGH.
4. WHEN the time between a Tender's publication and its submission_deadline is fewer than 3 calendar days, THE Fraud_Detection_Engine SHALL raise a Red_Flag of type SHORT_DEADLINE with severity MEDIUM.
5. WHEN two or more Bidders share the same registered address or director name in the company registry, THE Fraud_Detection_Engine SHALL raise a Red_Flag of type LINKED_ENTITIES with severity HIGH.
6. WHEN a Bidder submits bids in 3 or more Tenders in the same category within the same 30-day period and wins none of them, THE Fraud_Detection_Engine SHALL raise a Red_Flag of type COVER_BID_PATTERN with severity HIGH.
7. THE Fraud_Detection_Engine SHALL evaluate all applicable rules against a Tender record within 2 seconds of the record being stored.
8. THE Fraud_Detection_Engine SHALL support addition of new rule definitions by an Administrator without requiring a system restart.

---

### Requirement 4: Machine Learning Anomaly Detection

**User Story:** As a fraud analyst, I want the system to detect novel fraud patterns that do not match predefined rules, so that emerging collusion schemes are not missed.

*Justified by: R1 (coalition-based ML screens), R2 (Isolation Forest on OCDS data), R3 (9-feature neural network), R5 (bid-distribution screens).*

#### Acceptance Criteria

1. THE Fraud_Detection_Engine SHALL compute the following Bid_Screens for each Tender with 3 or more bids: coefficient of variation of bid amounts, bid-spread ratio (max bid / min bid), and normalized distance of the winning bid from the mean.
2. WHEN a trained ML model is available, THE Fraud_Detection_Engine SHALL apply an Isolation Forest model to the Bid_Screens of each Tender and produce an anomaly score in the range [0, 1].
3. WHEN a trained ML model is available, THE Fraud_Detection_Engine SHALL apply a Random Forest classifier to labeled historical Tender data and produce a collusion probability score in the range [0, 1].
4. THE Fraud_Detection_Engine SHALL retrain ML models on a schedule configurable by an Administrator, with a minimum retraining interval of 24 hours.
5. WHEN a Tender has fewer than 3 bids, THE Fraud_Detection_Engine SHALL set the ML anomaly score to null and rely solely on rule-based Red_Flags for that Tender.
6. THE Fraud_Detection_Engine SHALL log the model version, training date, and feature importances used for each scoring run to the Audit_Log.

---

### Requirement 5: Fraud Risk Scoring

**User Story:** As a procurement auditor, I want each tender to receive a single 0–100 Fraud Risk Score, so that I can quickly triage which tenders require urgent investigation.

*Justified by: G5 (World Bank ProACT multi-indicator scoring), R6 (systematic mapping of detection methods).*

#### Acceptance Criteria

1. THE Risk_Scorer SHALL compute a Fraud_Risk_Score for each Tender as a weighted aggregate of: active Red_Flag severities (HIGH = 25 points, MEDIUM = 10 points each, capped at 50), ML anomaly score × 30, and ML collusion probability × 20.
2. THE Risk_Scorer SHALL clamp the Fraud_Risk_Score to the integer range [0, 100].
3. WHEN a Tender's Fraud_Risk_Score is computed or updated, THE Risk_Scorer SHALL persist the score and the timestamp of computation to the database.
4. THE Risk_Scorer SHALL recompute a Tender's Fraud_Risk_Score within 5 seconds of any new bid record being ingested for that Tender.
5. THE Risk_Scorer SHALL recompute a Tender's Fraud_Risk_Score within 5 seconds of any Red_Flag being raised or cleared for that Tender.
6. WHERE an Administrator has configured custom weight overrides, THE Risk_Scorer SHALL apply the custom weights instead of the defaults defined in criterion 1.

---

### Requirement 6: Explainable AI (XAI) Justification

**User Story:** As a fraud analyst, I want to understand why a tender received a specific Fraud Risk Score, so that I can present evidence-backed findings to oversight bodies.

*Justified by: R8 (SHAP/LIME for fraud detection), L4 (EU AI Act explainability), ResearchGate (2024) XAI in compliance models.*

#### Acceptance Criteria

1. WHEN a Fraud_Risk_Score is computed for a Tender, THE XAI_Explainer SHALL generate a SHAP value attribution for each feature that contributed to the ML anomaly score and ML collusion probability score.
2. THE XAI_Explainer SHALL produce a human-readable explanation listing the top 5 contributing factors to the Fraud_Risk_Score, each expressed as a plain-language sentence (e.g., "Winning bid was 52% below the estimated value").
3. WHEN a user views a Tender's fraud detail page, THE Dashboard SHALL display the SHAP feature attribution chart and the plain-language explanation within 3 seconds of the page request.
4. THE XAI_Explainer SHALL include all active Red_Flags in the explanation output, with the rule text and the data values that triggered each flag.
5. THE XAI_Explainer SHALL version-stamp each explanation with the ML model version and rule engine version used, and store it in the Audit_Log.
6. IF the ML model produces a score but SHAP computation fails, THEN THE XAI_Explainer SHALL fall back to displaying only the Red_Flag explanations and log the SHAP failure to the Audit_Log.

---

### Requirement 7: Company Behavioral Tracking

**User Story:** As a fraud analyst, I want to view a company's historical bidding behavior across all tenders, so that I can identify long-term patterns of collusion or manipulation.

*Justified by: N3 (Mithi scam — 13-entity collusion ring), N5 (repeat-winner concentration), R4 (outcome-based detection).*

#### Acceptance Criteria

1. THE Behavioral_Tracker SHALL maintain a Company Risk Profile for each Bidder, updated within 10 seconds of any new bid or award record being ingested for that Bidder.
2. THE Behavioral_Tracker SHALL compute and store the following metrics per Company Risk Profile: total tenders bid, total tenders won, win rate percentage, average bid deviation from estimated value, number of active Red_Flags, and highest Fraud_Risk_Score across associated Tenders.
3. WHEN a Bidder's win rate in a single category exceeds 60% over a rolling 12-month window, THE Behavioral_Tracker SHALL set the Company Risk Profile status to HIGH_RISK.
4. WHEN a Bidder is linked to a Collusion_Ring detected by the Collusion_Graph, THE Behavioral_Tracker SHALL set the Company Risk Profile status to HIGH_RISK and record the Collusion_Ring identifier.
5. THE Dashboard SHALL display a Company Risk Profile page showing all metrics defined in criterion 2, a timeline of the Bidder's tender activity, and all associated Red_Flags.
6. THE Behavioral_Tracker SHALL retain Company Risk Profile history for a minimum of 5 years.

---

### Requirement 8: Collusion Network Graph

**User Story:** As a fraud analyst, I want to visualize relationships between companies that bid together, share directors, or share addresses, so that I can identify collusion rings.

*Justified by: R7 (GNN collusion detection), R9 (graph-oriented DB for procurement entities), R10 (network + ML combined), N3 (13-entity collusion ring).*

#### Acceptance Criteria

1. THE Collusion_Graph SHALL represent Bidders as nodes and co-bidding relationships as edges, where an edge is created when two Bidders submit bids on the same Tender.
2. THE Collusion_Graph SHALL add a SHARED_DIRECTOR edge between two Bidder nodes when they share a director name in the company registry data.
3. THE Collusion_Graph SHALL add a SHARED_ADDRESS edge between two Bidder nodes when they share a registered address.
4. WHEN a connected component in the Collusion_Graph contains 3 or more Bidder nodes connected by HIGH-severity Red_Flag edges, THE Collusion_Graph SHALL classify that component as a Collusion_Ring and assign it a unique identifier.
5. THE Dashboard SHALL render the Collusion_Graph as an interactive force-directed visualization, allowing users to zoom, pan, filter by edge type, and click nodes to navigate to the corresponding Company Risk Profile.
6. THE Collusion_Graph SHALL update within 30 seconds of new bid or company registry data being ingested.
7. WHEN a Collusion_Ring is identified, THE Collusion_Graph SHALL trigger the Alert_System with severity HIGH.

---

### Requirement 9: Tender Dashboard

**User Story:** As a procurement auditor, I want a central dashboard showing all tenders with their risk scores and status, so that I can efficiently manage my review workload.

#### Acceptance Criteria

1. THE Dashboard SHALL display a paginated list of all Tenders, sortable by Fraud_Risk_Score (descending by default), submission_deadline, category, and buyer_name.
2. THE Dashboard SHALL provide a filter panel allowing users to filter Tenders by: Fraud_Risk_Score range, category, buyer_name, date range, and Red_Flag type.
3. WHEN a user applies a filter, THE Dashboard SHALL update the Tender list within 1 second.
4. THE Dashboard SHALL display summary statistics at the top of the Tender list: total tenders analyzed, number with Fraud_Risk_Score ≥ 70, number with active HIGH-severity Red_Flags, and number of identified Collusion_Rings.
5. THE Dashboard SHALL display each Tender row with: tender_id, title, category, Fraud_Risk_Score (color-coded: green 0–39, amber 40–69, red 70–100), active Red_Flag count, and submission_deadline.
6. THE Dashboard SHALL be responsive and render correctly on screen widths from 1024px to 2560px.
7. THE Dashboard SHALL load the initial Tender list within 2 seconds for datasets of up to 50,000 Tender records.

---

### Requirement 10: Alerts and Notifications

**User Story:** As a procurement auditor, I want to receive real-time alerts when high-risk tenders are detected, so that I can act before a fraudulent contract is awarded.

#### Acceptance Criteria

1. THE Alert_System SHALL send an in-app notification to all users with the Auditor or Administrator role when a Tender's Fraud_Risk_Score reaches or exceeds a threshold configurable per user (default: 70).
2. WHERE email notifications are enabled by an Administrator, THE Alert_System SHALL send an email notification to the configured recipient list within 60 seconds of a threshold-crossing event.
3. WHEN an alert is generated, THE Alert_System SHALL include in the notification: tender_id, title, Fraud_Risk_Score, top 3 contributing Red_Flags, and a direct link to the Tender detail page.
4. THE Alert_System SHALL maintain an alert history log accessible to Auditor and Administrator roles, showing all alerts generated in the past 90 days.
5. IF the email delivery service is unavailable, THEN THE Alert_System SHALL retry delivery up to 3 times at 5-minute intervals and log each failed attempt to the Audit_Log.
6. THE Alert_System SHALL allow an Administrator to configure per-category alert thresholds independently of the global threshold.

---

### Requirement 11: Audit Logging and Compliance Export

**User Story:** As a compliance officer, I want a complete, tamper-evident audit trail of all system actions, so that findings can be submitted to oversight bodies and RTI requests.

*Justified by: L3 (Right to Information Act), L1 (Indian Competition Act — advisory-only scores), L4 (EU AI Act audit requirements).*

#### Acceptance Criteria

1. THE TenderShield SHALL write an Audit_Log entry for every event of the following types: user login/logout, tender ingestion, score computation, Red_Flag raised/cleared, alert sent, and user-initiated status change on a Tender.
2. THE Audit_Log SHALL record for each entry: event_type, timestamp (UTC), user_id, affected_entity_id, and a JSON snapshot of the relevant data at the time of the event.
3. THE TenderShield SHALL prevent modification or deletion of Audit_Log entries by any user role, including Administrator.
4. WHEN a compliance officer requests an audit export, THE TenderShield SHALL generate a PDF report containing all Audit_Log entries for a specified date range within 30 seconds.
5. THE TenderShield SHALL retain Audit_Log entries for a minimum of 7 years.
6. THE Dashboard SHALL display a disclaimer on all Fraud_Risk_Score outputs stating: "This score is advisory only. Human review is required before initiating any legal or administrative action."

---

### Requirement 12: API Security

**User Story:** As a system administrator, I want all API endpoints to be secured against common web vulnerabilities, so that fraud intelligence data is not exposed or tampered with.

#### Acceptance Criteria

1. THE TenderShield SHALL require a valid JWT in the Authorization header for all API endpoints except the authentication endpoint.
2. THE TenderShield SHALL enforce HTTPS for all API communication and reject HTTP requests with an HTTP 301 redirect.
3. THE TenderShield SHALL implement rate limiting on all API endpoints, rejecting requests exceeding 100 requests per minute per authenticated user with an HTTP 429 response.
4. THE TenderShield SHALL validate and sanitize all user-supplied input on API endpoints to prevent SQL injection and cross-site scripting attacks.
5. THE TenderShield SHALL include CORS headers restricting API access to the configured frontend origin domain.
6. IF an API request contains a JWT signed with an unrecognized key, THEN THE TenderShield SHALL return an HTTP 401 response and log the event to the Audit_Log.

---

### Requirement 13: Deployment and Operations

**User Story:** As a DevOps engineer, I want the platform to be containerized and deployable via CI/CD, so that updates can be released reliably and the system can be reproduced in any environment.

#### Acceptance Criteria

1. THE TenderShield SHALL provide a Docker Compose configuration that starts all services (Next.js frontend, Django backend, MySQL database, ML worker) with a single `docker-compose up` command.
2. THE TenderShield SHALL provide a CI/CD pipeline configuration (GitHub Actions) that runs automated tests and builds Docker images on every push to the main branch.
3. WHEN the Docker Compose stack starts, THE TenderShield SHALL complete health checks for all services within 60 seconds.
4. THE TenderShield SHALL provide a setup guide documenting: environment variable configuration, database migration steps, initial admin user creation, and ML model training invocation.
5. THE TenderShield SHALL expose a `/health` endpoint on the backend that returns HTTP 200 with service status when all dependent services are reachable, and HTTP 503 when any dependent service is unreachable.
6. THE TenderShield SHALL support zero-downtime deployment by running database migrations before routing traffic to the new backend container version.
