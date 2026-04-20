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

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16, TypeScript, Tailwind CSS |
| UI System | HeroUI v3 (layout/sidebar/tables), framer-motion (animations) |
| Charts | Recharts via Chakra UI Charts |
| Backend | Django 4.2, Django REST Framework, Gunicorn |
| Auth | JWT RS256 via djangorestframework-simplejwt |
| Database | MySQL 8 |
| Cache / Broker | Redis 7 |
| Task Queue | Celery |
| ML | scikit-learn (Isolation Forest, Random Forest), SHAP, pandas |

---

## Quick Start (Local Development)

### Prerequisites

- Python 3.11+
- Node.js 20+
- MySQL 8 running locally
- Redis running locally (optional — only needed for ML/Celery tasks)

### 1. Clone and configure environment

```bash
cp .env.example .env
```

Edit `.env` — the key values for local dev:

```env
DB_HOST=127.0.0.1
DB_PORT=3306
REDIS_URL=redis://127.0.0.1:6379/0
NEXT_PUBLIC_API_URL=http://localhost:8000
DEBUG=True
```

See [`docs/setup.md`](docs/setup.md) for JWT key generation instructions.

### 2. Set up the database

Create the MySQL database and user:

```sql
CREATE DATABASE tendershield;
CREATE USER 'tendershield'@'localhost' IDENTIFIED BY 'changeme_db';
GRANT ALL PRIVILEGES ON tendershield.* TO 'tendershield'@'localhost';
FLUSH PRIVILEGES;
```

### 3. Start the backend

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py create_superuser_admin --username admin --email admin@example.com --password "ChangeMe123!"
python manage.py runserver
```

Backend runs at `http://localhost:8000`

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`

### 5. Open the app

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000/api/v1/ |
| Django Admin | http://localhost:8000/admin |
| Health Check | http://localhost:8000/health |

**Default credentials admin:** `admin` / `ChangeMe123!`
**Default credentials auditor:** `auditor` / `Auditor@123`
**Default credentials agency_admin:** `bobibi5620_3` / `AgencyAdmin@123`
**Default credentials agency_officer:** `agency_officer` / `Officer@123`
**Default credentials reviewer:** `reviewer` / `Reviewer@123`
**Default credentials government_audiror:** `gov_auditor` / `GovAudit@123`

> Change the password after first login.

---

## Project Structure

```
├── backend/           # Django API (auth, tenders, bids, detection, scoring, alerts, audit)
├── frontend/          # Next.js app (dashboard, tenders, companies, graph, alerts, audit)
│   ├── app/           # Next.js App Router pages
│   ├── components/
│   │   ├── charts/    # Recharts-based data visualisation
│   │   ├── tables/    # Tender and bid tables
│   │   └── ui/        # Reusable UI components
│   ├── contexts/      # Auth context
│   ├── lib/           # Axios API client
│   └── types/         # TypeScript interfaces
├── ml_worker/         # Celery worker — ML training and inference
├── docs/
│   ├── setup.md       # Environment variables, JWT keys, migrations
│   ├── deployment.md  # Production deployment guide
│   └── USER_GUIDE.md  # Full feature and API documentation
├── .env.example
└── docker-compose.yml # Legacy — kept for reference, not required for local dev
```

---

## Frontend Pages

| Route | Description |
|---|---|
| `/dashboard` | KPI cards, fraud trend chart, risk distribution, tender feed |
| `/tenders` | Full tender list with filters and risk score badges |
| `/tenders/[id]` | Tender detail — score card, SHAP chart, red flags, bid table |
| `/companies` | Company risk profiles table |
| `/companies/[id]` | Company detail — metrics, tender timeline, red flags |
| `/graph` | Interactive collusion network graph |
| `/alerts` | Alert inbox with delivery status |
| `/audit` | Audit log table with PDF export (Admin only) |

---

## API

Base URL: `http://localhost:8000/api/v1/`

All endpoints require `Authorization: Bearer <token>` except login.

| Endpoint | Description |
|---|---|
| `POST /auth/login/` | Login — returns access + refresh tokens |
| `POST /auth/logout/` | Blacklist token |
| `POST /auth/refresh/` | Refresh access token |
| `GET /tenders/` | List tenders with fraud scores |
| `GET /tenders/stats/` | Dashboard KPI stats |
| `GET /tenders/{id}/score/` | Fraud risk score |
| `GET /tenders/{id}/explanation/` | SHAP explanation + red flags |
| `GET /bids/` | List bids |
| `GET /companies/` | Company risk profiles |
| `GET /companies/{id}/tenders/` | Company tender history |
| `GET /companies/{id}/red-flags/` | Company red flags |
| `GET /graph/` | Collusion graph nodes + edges |
| `GET /graph/rings/` | Detected collusion rings |
| `GET /alerts/` | Alert inbox |
| `POST /alerts/{id}/read/` | Mark alert as read |
| `GET /audit-log/` | Audit log (Admin only) |
| `POST /audit-log/export/` | Queue PDF export |

Full API reference: [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md)

---

## User Roles

| Role | Access |
|---|---|
| **ADMIN** | Full access — ingest data, manage rules, configure alerts, view audit log |
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

---

## Documentation

- [`docs/setup.md`](docs/setup.md) — environment variables, JWT key generation, migrations
- [`docs/deployment.md`](docs/deployment.md) — production deployment
- [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) — full user guide and API reference

---

> **Advisory:** All fraud risk scores are advisory only. Human review is required before initiating any legal or administrative action.
