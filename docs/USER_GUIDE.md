# TenderShield — Complete User Guide

> **Advisory Disclaimer:** All fraud risk scores are advisory only. Human review is required before initiating any legal or administrative action.

---

## Table of Contents

1. [What is TenderShield?](#1-what-is-tendershield)
2. [Quick Start & Default Credentials](#2-quick-start--default-credentials)
3. [Setup & Installation](#3-setup--installation)
4. [User Roles & Permissions](#4-user-roles--permissions)
5. [Frontend Pages](#5-frontend-pages)
6. [Features In Depth](#6-features-in-depth)
7. [API Reference](#7-api-reference)
8. [ML Scoring System](#8-ml-scoring-system)
9. [Alert System](#9-alert-system)
10. [Audit Log](#10-audit-log)
11. [Administration](#11-administration)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. What is TenderShield?

TenderShield is a fraud detection platform for public procurement tenders. It ingests tender and bid data, runs a rule-based detection engine and ML models to compute fraud risk scores, visualises bidder collusion networks, and sends alerts when suspicious activity is detected.

**Core capabilities:**
- Ingest tenders individually or via CSV batch upload
- Automatically detect 6 types of fraud red flags via rule engine
- Score each tender 0–100 using a hybrid rule + ML model
- Visualise bidder relationships as an interactive graph
- Track company risk profiles over time
- Send email alerts when scores exceed configurable thresholds
- Immutable audit log of all system events

---

## 2. Quick Start & Default Credentials

# Check if everything is running/healthy
```
docker compose ps
```

# View live logs (Ctrl+C to exit)
```
docker compose logs -f
```

# Restart a single service (e.g. after a code change)
```
docker compose restart backend
```

# Stop but keep the database data
```
docker compose down
```

# Stop AND wipe the database volume (full reset)
```
docker compose down -v
```

Start the project:
```
docker compose up -d
```


Stop the project:
```
docker compose down
```

### Default Admin Account

| Field    | Value            |
|----------|------------------|
| Username | `admin`          |
| Password | `ChangeMe123!`   |
| Role     | Administrator    |
| URL      | http://localhost:3000/login |

> **Change this password immediately after first login.** The account locks after 5 failed attempts within 10 minutes.

### Service URLs

| Service       | URL                          |
|---------------|------------------------------|
| Frontend      | http://localhost:3000        |
| Backend API   | http://localhost:8000        |
| Django Admin  | http://localhost:8000/admin  |
| Health Check  | http://localhost:8000/health |

---

## 3. Setup & Installation

### Prerequisites

- Docker 24.x
- Docker Compose v2
- Python (for key generation during setup)

### Step-by-step

**1. Clone and enter the project directory**

**2. Generate the `.env` file**

The `.env` file is pre-configured if you followed the automated setup. To set it up manually:

```bash
cp .env.example .env
```

Then fill in:
- `SECRET_KEY` — generate with Python: `python -c "import secrets; print(secrets.token_urlsafe(50))"`
- `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` — RS256 key pair (see `docs/setup.md` for generation steps)
- Database passwords, SMTP credentials

**3. Start the database and Redis first**

```bash
docker compose up -d db redis
```

Wait until both show `(healthy)`:
```bash
docker compose ps
```

**4. Run database migrations**

```bash
docker compose run --rm backend python manage.py migrate
```

**5. Create the admin user**

```bash
docker compose run --rm backend \
  python manage.py create_superuser_admin \
  --username admin \
  --email admin@example.com \
  --password "ChangeMe123!"
```

**6. Start the full stack**

```bash
docker compose up -d
```

**7. Verify everything is healthy**

```bash
# PowerShell
Invoke-RestMethod -Uri "http://localhost:8000/health"

# curl
curl http://localhost:8000/health
```

Expected response:
```json
{ "status": "ok", "db": "ok", "redis": "ok", "ml_worker": "ok" }
```

**8. Open the app**

Navigate to http://localhost:3000 — you'll be redirected to the login page.

---

## 4. User Roles & Permissions

TenderShield has two roles. Every user must have one.

### ADMIN (Administrator)

Full read-write access to everything.

| Capability | Details |
|---|---|
| Ingest tenders | Single POST or CSV batch upload |
| Ingest bids | Single or bulk |
| Manage rules | Add new fraud detection rules at runtime |
| Change tender status | ACTIVE → CLOSED / AWARDED / CANCELLED |
| Trigger rescore | Manually re-run scoring on a tender |
| Configure alerts | Set thresholds and email preferences |
| View audit log | Full log with PDF export |
| Django admin panel | `/admin/` access |

### AUDITOR

Read-only access to all data. Cannot modify anything.

| Capability | Details |
|---|---|
| View tenders | List and detail with scores |
| View bids | Per-tender bid list |
| View red flags | Per-tender flag list |
| View companies | Company profiles and risk status |
| View graph | Collusion network visualisation |
| View alerts | Their own alerts only |
| View score history | Historical score trend per tender |

### Creating Additional Users

Use the Django admin panel at http://localhost:8000/admin:

1. Log in with admin credentials
2. Go to **Authentication → Users → Add User**
3. Set username, email, password
4. Set **Role** to `AUDITOR` or `ADMIN`
5. Save

---

## 5. Frontend Pages

### `/login`
Login form. Enter username and password. After 5 failed attempts the account locks for 10 minutes.

### `/dashboard`
Main overview page. Shows:
- Summary stats: total tenders, high-risk count, active red flags, alerts sent
- Filterable, sortable tender table with fraud risk scores
- Filter by: score range, category, buyer name, date range, flag type
- Click any tender row to open its detail page

### `/tenders/[id]`
Tender detail page. Shows:
- Tender metadata (ID, title, category, buyer, estimated value, deadline, status)
- Current fraud risk score with colour-coded badge (green/amber/red)
- SHAP explanation chart — which factors contributed most to the score
- Active red flags list with severity and trigger details
- Bid table — all bids with amounts, bidder names, winner flag
- Score history — chart of how the score changed over time

### `/companies`
Company/bidder profiles. Shows:
- Paginated list of all bidders with risk status badges
- Columns: bidder name, total bids, wins, win rate, active red flags, highest score, risk status
- Filter by risk status (LOW / MEDIUM / HIGH_RISK) or bidder name
- Click a company to see their tenders and red flags

### `/graph`
Interactive collusion network graph. Shows:
- Nodes = bidders, edges = relationships
- Edge types: Co-bid (indigo), Shared Director (amber), Shared Address (emerald)
- Toggle edge type filters to focus on specific relationship types
- Collusion rings panel — detected groups of colluding bidders
- Click a ring to highlight its members in the graph

### `/alerts`
Alert inbox. Shows:
- All alerts from the last 90 days
- Alert types: High Risk Score, Collusion Ring Detected, Red Flag Raised
- Mark alerts as read
- Admins can configure alert thresholds and email settings

### `/audit`
Audit log viewer (Admin only). Shows:
- Immutable log of all system events
- Filter by event type, user, date range
- Export to PDF for a date range

---

## 6. Features In Depth

### Tender Ingestion

**Single tender** (Admin only):
```
POST /api/v1/tenders/
```
Required fields: `tender_id`, `title`, `category`, `estimated_value`, `currency`, `submission_deadline`, `buyer_id`, `buyer_name`

**CSV batch upload** (Admin only):
```
POST /api/v1/tenders/upload/
```
Upload a CSV file with the same required columns. The system:
- Validates every row
- Rejects rows with missing mandatory fields
- Rejects duplicate `tender_id` values
- Returns a validation report listing rejected rows with reasons
- Stores valid rows (supports 10,000+ rows per batch)

After ingestion, scoring and rule evaluation run automatically via background tasks.

### Fraud Detection Rules

Six rules run automatically whenever bids are ingested:

| Rule | Trigger | Severity |
|---|---|---|
| **SINGLE_BIDDER** | Only 1 bidder at submission deadline | HIGH |
| **PRICE_ANOMALY** | Winning bid deviates >40% from estimated value | MEDIUM |
| **REPEAT_WINNER** | Same bidder wins >60% of tenders in a category within 12 months | HIGH |
| **SHORT_DEADLINE** | Time between publication and deadline < 3 calendar days | MEDIUM |
| **LINKED_ENTITIES** | Two or more bidders share address or director name | HIGH |
| **COVER_BID_PATTERN** | Bidder submits bids in 3+ tenders in same category within 30 days with 0 wins | HIGH |

Admins can add new rules at runtime via `POST /api/v1/rules/` without restarting the system.

### Fraud Risk Score

Each tender gets a score from **0 to 100**:

- **0–39** — Low risk (green)
- **40–69** — Medium risk (amber)
- **70–100** — High risk (red)

The score combines:
- Rule-based red flag contribution (weighted by severity)
- ML anomaly score from Isolation Forest
- ML collusion score from Random Forest

Admins can adjust scoring weights via the Django admin panel (`ScoringWeightConfig`).

### SHAP Explanations

Every scored tender has a SHAP explanation showing which features drove the score. Visible on the tender detail page as a bar chart. Features include:
- `cv_bids` — coefficient of variation of bid amounts
- `bid_spread_ratio` — spread between highest and lowest bid
- `norm_winning_distance` — how far the winning bid is from the mean
- `single_bidder_flag` — binary flag
- `price_deviation_pct` — % deviation from estimated value
- `deadline_days` — days between publication and deadline
- `repeat_winner_rate` — winner's historical win rate in category
- `bidder_count` — number of bidders
- `winner_bid_rank` — rank of winning bid by amount

### Collusion Graph

The graph maps relationships between bidders:
- **Co-bid edges** — two bidders competed in the same tender
- **Shared Director edges** — bidders share a director name
- **Shared Address edges** — bidders share a registered address

The system automatically detects **collusion rings** — clusters of bidders with dense interconnections. Each ring shows member count and detection date.

### Company Profiles

Every bidder gets a profile tracking:
- Total bids and wins
- Win rate
- Average bid deviation from estimated values
- Active red flag count
- Highest fraud risk score ever seen
- Risk status: LOW / MEDIUM / HIGH_RISK
- Collusion ring membership (if detected)

Profiles update automatically after each bid ingestion.

---

## 7. API Reference

All API endpoints are under `http://localhost:8000/api/v1/`.

Authentication: `Authorization: Bearer <access_token>`

### Auth

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/auth/login/` | Public | Login, returns `{access, refresh, expires_in, role}` |
| POST | `/auth/logout/` | Any | Blacklist token |
| POST | `/auth/refresh/` | Any | Get new access token from refresh token |

**Login example:**
```bash
curl -X POST http://localhost:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "ChangeMe123!"}'
```

### Tenders

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/tenders/` | Auditor, Admin | List tenders (paginated, filterable) |
| POST | `/tenders/` | Admin | Create single tender |
| POST | `/tenders/upload/` | Admin | CSV batch upload |
| GET | `/tenders/stats/` | Auditor, Admin | Dashboard summary stats |
| GET | `/tenders/{id}/` | Auditor, Admin | Tender detail |
| GET | `/tenders/{id}/score/` | Auditor, Admin | Current fraud risk score |
| GET | `/tenders/{id}/explanation/` | Auditor, Admin | SHAP explanation |
| GET | `/tenders/{id}/red-flags/` | Auditor, Admin | Active red flags |
| GET | `/tenders/{id}/score-history/` | Auditor, Admin | Historical scores |
| POST | `/tenders/{id}/rescore/` | Admin | Trigger manual rescore |
| PATCH | `/tenders/{id}/status/` | Admin | Change tender status |

**Tender list filters:**
- `score_min`, `score_max` — filter by fraud score range
- `category` — filter by category string
- `buyer_name` — partial match on buyer name
- `date_from`, `date_to` — filter by submission deadline
- `flag_type` — filter by red flag type
- `ordering` — e.g. `-score`, `submission_deadline`
- `page`, `page_size`

### Bids

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/bids/?tender_id={id}` | Auditor, Admin | List bids for a tender |
| POST | `/bids/` | Admin | Create single bid |
| POST | `/bids/bulk/` | Admin | Bulk bid ingestion |

### Companies

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/companies/` | Auditor, Admin | List company profiles |
| GET | `/companies/{id}/` | Auditor, Admin | Company detail |
| GET | `/companies/{id}/tenders/` | Auditor, Admin | Tenders this company bid on |
| GET | `/companies/{id}/red-flags/` | Auditor, Admin | Red flags for this company |

**Company list filters:** `risk_status`, `bidder_name`

### Graph

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/graph/` | Auditor, Admin | Full graph (nodes + edges) |
| GET | `/graph/?edge_type=CO_BID` | Auditor, Admin | Filtered by edge type |
| GET | `/graph/rings/` | Auditor, Admin | All collusion rings |
| GET | `/graph/rings/{ring_id}/` | Auditor, Admin | Ring detail |

### Alerts

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/alerts/` | Auditor, Admin | List alerts (last 90 days) |
| GET | `/alerts/unread/` | Auditor, Admin | Unread alerts |
| GET | `/alerts/{id}/` | Auditor, Admin | Alert detail |
| POST | `/alerts/{id}/read/` | Auditor, Admin | Mark as read |
| GET | `/alerts/settings/` | Admin | Get alert settings |
| POST | `/alerts/settings/` | Admin | Create/update alert settings |

### Rules

| Method | Endpoint | Access | Description |
|---|---|---|---|
| POST | `/rules/` | Admin | Add new rule definition |

### Audit Log

| Method | Endpoint | Access | Description |
|---|---|---|---|
| GET | `/audit-log/` | Admin | Paginated audit log |
| POST | `/audit-log/export/` | Admin | Queue PDF export |
| GET | `/audit-log/export/{task_id}/status/` | Admin | Poll export status / get download URL |

**Audit log filters:** `event_type`, `user_id`, `date_from`, `date_to`

---

## 8. ML Scoring System

### How it works

1. When bids are ingested, a Celery task computes a 9-feature vector for the tender
2. Two models score the tender:
   - **Isolation Forest** — anomaly detection (unsupervised)
   - **Random Forest** — collusion classification (supervised)
3. Scores are combined with rule-based red flag contributions into a final 0–100 score
4. SHAP values explain which features drove the score

### ML scores are `null` when:
- Fewer than 3 bids exist for the tender
- No trained model versions are active yet (fresh install)

### Initial model training

On a fresh install, trigger training manually after ingesting at least 10 tenders with bids:

```bash
docker compose run --rm ml-worker \
  python -c "
from ml_worker.tasks import retrain_models
result = retrain_models.apply()
print(result.get())
"
```

### Scheduled retraining

Models retrain automatically every 24 hours (configurable via `ML_RETRAIN_INTERVAL_HOURS` in `.env`, minimum 24h).

### Checking active model versions

```bash
docker compose run --rm backend \
  python manage.py shell -c "
from xai.models import MLModelVersion
for v in MLModelVersion.objects.filter(is_active=True):
    print(v.model_type, v.version, v.trained_at)
"
```

---

## 9. Alert System

### How alerts are triggered

An alert is created when a tender's fraud risk score exceeds the configured threshold (default: 70). Alert types:
- **HIGH_RISK_SCORE** — score crossed the threshold
- **COLLUSION_RING** — bidder added to a detected collusion ring
- **RED_FLAG** — a new red flag was raised

### Email delivery

Alerts are sent via email using the SMTP settings in `.env`. Delivery is handled by Celery with automatic retry (up to 3 attempts). After 3 failures the alert is marked `PERMANENTLY_FAILED`.

### Configuring thresholds

Admins can set per-user, per-category thresholds:

```bash
POST /api/v1/alerts/settings/
{
  "threshold": 65,
  "category": "Construction",
  "email_enabled": true
}
```

Leave `category` empty for a global threshold.

### Alert statuses

| Status | Meaning |
|---|---|
| PENDING | Queued for delivery |
| DELIVERED | Email sent successfully |
| FAILED | Delivery failed, will retry |
| RETRYING | Retry in progress |
| PERMANENTLY_FAILED | All 3 retries exhausted |

---

## 10. Audit Log

Every significant action is recorded in an immutable audit log. Entries **cannot be edited or deleted** (7-year retention policy).

### Logged events

| Event | Trigger |
|---|---|
| USER_LOGIN | Successful login |
| USER_LOGOUT | Logout |
| USER_LOGIN_FAILED | Failed login attempt |
| USER_LOCKED | Account locked after 5 failures |
| TENDER_INGESTED | Tender created |
| BID_INGESTED | Bid created |
| SCORE_COMPUTED | Fraud score calculated |
| RED_FLAG_RAISED | Rule triggered a red flag |
| RED_FLAG_CLEARED | Red flag deactivated |
| ALERT_SENT | Alert email delivered |
| ALERT_FAILED | Alert email failed |
| STATUS_CHANGED | Tender status changed |
| MODEL_RETRAINED | ML models retrained |
| EXPORT_GENERATED | PDF audit export created |
| RULE_ADDED | New rule definition added |

### Exporting to PDF

```bash
# 1. Queue the export
curl -X POST http://localhost:8000/api/v1/audit-log/export/ \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"date_from": "2026-01-01", "date_to": "2026-12-31"}'
# Returns: {"task_id": "abc123", "status": "queued"}

# 2. Poll for completion
curl http://localhost:8000/api/v1/audit-log/export/abc123/status/ \
  -H "Authorization: Bearer <token>"
# Returns when done: {"status": "complete", "download_url": "/media/exports/audit_....pdf"}
```

---

## 11. Administration

### Django Admin Panel

Access at http://localhost:8000/admin with admin credentials.

Useful admin sections:
- **Authentication → Users** — manage users, roles, reset passwords
- **Scoring → Scoring weight configs** — adjust ML/rule weighting
- **Detection → Rule definitions** — view/edit fraud detection rules
- **Xai → ML model versions** — view trained model history

### Changing the Admin Password

Via the web UI: go to http://localhost:3000, log in, and use the profile settings.

Via Django admin: http://localhost:8000/admin → Users → admin → change password.

Via CLI:
```bash
docker compose run --rm backend \
  python manage.py changepassword admin
```

### Creating an Auditor User

```bash
docker compose run --rm backend python manage.py shell -c "
from authentication.models import User, UserRole
User.objects.create_user(
    username='auditor1',
    email='auditor1@example.com',
    password='SecurePass123!',
    role=UserRole.AUDITOR
)
print('Auditor created')
"
```

### Stopping and Starting Services

```bash
# Stop everything
docker compose down

# Start everything
docker compose up -d

# Restart a single service
docker compose restart backend

# View logs
docker compose logs -f backend
docker compose logs -f ml-worker
docker compose logs -f frontend
```

### Updating After Code Changes

```bash
# Rebuild and restart a service
docker compose build backend
docker compose up -d backend

# Run new migrations after a backend update
docker compose run --rm backend python manage.py migrate
```

---

## 12. Troubleshooting

### Health check returns degraded

```bash
Invoke-RestMethod http://localhost:8000/health
```

Check which service is `"error"` and inspect its logs:
```bash
docker compose logs db
docker compose logs redis
docker compose logs ml-worker
```

### Can't log in

- Verify the backend is running: `docker compose ps`
- Check the account isn't locked (5 failed attempts = 10 min lockout)
- Reset via Django admin or CLI: `docker compose run --rm backend python manage.py changepassword admin`

### ML scores are null

- Not enough data: need at least 10 tenders with 3+ bids each before training
- Trigger training manually (see [ML Scoring System](#8-ml-scoring-system))
- Check ml-worker logs: `docker compose logs ml-worker`

### Port 3306 conflict

If MySQL is already running locally, the DB port is remapped to `3307` in `docker-compose.yml`. The app connects internally via the Docker network so this doesn't affect functionality.

### Frontend shows default Next.js page

The root page redirects to `/login`. If you see the default Next.js placeholder, the frontend image needs to be rebuilt:
```bash
docker compose build frontend
docker compose up -d frontend
```

### Email alerts not sending

Check SMTP settings in `.env`:
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`

For local development without a real SMTP server, you can use [Mailpit](https://mailpit.axllent.org/) or set `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` in settings to print emails to the console.
