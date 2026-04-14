# TenderShield

AI-powered procurement fraud detection platform. Ingests tender and bid data, runs a rule-based detection engine alongside ML models, visualises bidder collusion networks, and sends alerts when suspicious activity is detected.

---

## Features

- **Fraud Detection Engine** — 6 rule types: single bidder, price anomaly, repeat winner, short deadline, linked entities, cover bid pattern
- **ML Scoring** — Isolation Forest (anomaly) + Random Forest (collusion) produce a 0–100 fraud risk score per tender
- **SHAP Explanations** — per-tender breakdown of which features drove the score
- **Collusion Graph** — interactive network visualising bidder relationships (co-bids, shared directors, shared addresses)
- **Company Profiles** — risk tracking per bidder across all tenders
- **Alert System** — email notifications when scores exceed configurable thresholds
- **Audit Log** — immutable, tamper-evident log of all system events with PDF export
- **Role-based access** — ADMIN (full access) and AUDITOR (read-only)

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, Tailwind CSS, vis-network |
| Backend | Django 4.2, Django REST Framework, Gunicorn |
| Auth | JWT RS256 via djangorestframework-simplejwt |
| Database | MySQL 8 |
| Cache / Broker | Redis 7 |
| Task Queue | Celery |
| ML | scikit-learn (Isolation Forest, Random Forest), SHAP, pandas |
| Infrastructure | Docker, Docker Compose |

---

## Quick Start

### Prerequisites

- Docker 24+
- Docker Compose v2

### 1. Configure environment

```bash
cp .env.example .env
```

The `.env` file needs a Django secret key and RS256 JWT key pair. See [`docs/setup.md`](docs/setup.md) for generation instructions. For a quick local run the example values work as-is except for the JWT keys.

### 2. Start the database

```bash
docker compose up -d db redis
```

Wait until both show `(healthy)`:

```bash
docker compose ps
```

### 3. Run migrations and create admin user

```bash
docker compose run --rm backend python manage.py migrate

docker compose run --rm backend \
  python manage.py create_superuser_admin \
  --username admin \
  --email admin@example.com \
  --password "ChangeMe123!"
```

### 4. Start everything

```bash
docker compose up -d
```

### 5. Open the app

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| Django Admin | http://localhost:8000/admin |
| Health Check | http://localhost:8000/health |

**Default credentials:** `admin` / `ChangeMe123!`

> Change the password after first login.

---

## Running & Stopping

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# Check status
docker compose ps

# View logs
docker compose logs -f
```

---

## Project Structure

```
├── backend/          # Django API (authentication, tenders, bids, detection, scoring, alerts, audit…)
├── frontend/         # Next.js app (dashboard, tenders, companies, graph, alerts, audit)
├── ml_worker/        # Celery worker — ML training and inference tasks
├── docs/
│   ├── setup.md      # Detailed setup and configuration guide
│   ├── deployment.md # Production deployment guide
│   └── USER_GUIDE.md # Full feature and API documentation
├── docker-compose.yml
└── .env.example
```

---

## API

Base URL: `http://localhost:8000/api/v1/`

All endpoints require `Authorization: Bearer <token>` except login.

| Endpoint | Description |
|---|---|
| `POST /auth/login/` | Login — returns access + refresh tokens |
| `POST /auth/logout/` | Blacklist token |
| `POST /auth/refresh/` | Refresh access token |
| `GET/POST /tenders/` | List or create tenders |
| `POST /tenders/upload/` | CSV batch upload (10k+ rows) |
| `GET /tenders/{id}/score/` | Fraud risk score |
| `GET /tenders/{id}/explanation/` | SHAP explanation |
| `GET /tenders/{id}/red-flags/` | Active red flags |
| `GET/POST /bids/` | List or create bids |
| `GET /companies/` | Company risk profiles |
| `GET /graph/` | Collusion graph data |
| `GET /graph/rings/` | Detected collusion rings |
| `GET /alerts/` | Alert inbox |
| `GET /audit-log/` | Audit log (Admin only) |
| `POST /audit-log/export/` | Queue PDF export |

Full API reference: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md#7-api-reference)

---

## User Roles

| Role | Access |
|---|---|
| **ADMIN** | Full read-write — ingest data, manage rules, configure alerts, view audit log |
| **AUDITOR** | Read-only — view tenders, scores, companies, graph, own alerts |

---

## Fraud Detection Rules

| Rule | Trigger | Severity |
|---|---|---|
| SINGLE_BIDDER | Only 1 bidder at deadline | HIGH |
| PRICE_ANOMALY | Winning bid deviates >40% from estimated value | MEDIUM |
| REPEAT_WINNER | Same bidder wins >60% in a category within 12 months | HIGH |
| SHORT_DEADLINE | Publication to deadline < 3 days | MEDIUM |
| LINKED_ENTITIES | Bidders share address or director | HIGH |
| COVER_BID_PATTERN | Bidder bids in 3+ tenders in 30 days with 0 wins | HIGH |

Rules run automatically on bid ingestion. Admins can add new rules at runtime via `POST /api/v1/rules/`.

---

## Documentation

- [`docs/setup.md`](docs/setup.md) — environment variables, JWT key generation, migrations, ML training
- [`docs/deployment.md`](docs/deployment.md) — production deployment
- [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — full user guide, all features, complete API reference

---

> **Advisory:** All fraud risk scores are advisory only. Human review is required before initiating any legal or administrative action.
