# TenderShield — Setup Guide

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Variable Configuration](#environment-variable-configuration)
3. [Database Migration Steps](#database-migration-steps)
4. [Initial Admin User Creation](#initial-admin-user-creation)
5. [ML Model Training Invocation](#ml-model-training-invocation)
6. [PDF Export Setup](#pdf-export-setup)
7. [Verifying the Installation](#verifying-the-installation)

---

## Prerequisites

| Requirement | Minimum Version |
|---|---|
| Docker | 24.x |
| Docker Compose | v2 (`docker compose` command) |
| `openssl` | any recent version |
| `curl` | for smoke-testing the health endpoint |

---

## Environment Variable Configuration

### 1. Copy the example file

```bash
cp .env.example .env
```

### 2. Generate the Django secret key

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Paste the output as the value of `SECRET_KEY` in `.env`.

### 3. Generate the RS256 JWT key pair

TenderShield signs JWTs with RS256 (asymmetric). Generate a 2048-bit key pair:

```bash
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
```

Encode the PEM files as single-line strings (literal `\n` for newlines) and paste into `.env`:

```bash
# On Linux / macOS
JWT_PRIVATE_KEY="$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' private.pem)"
JWT_PUBLIC_KEY="$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' public.pem)"
```

Delete the `.pem` files from disk after copying the values:

```bash
rm private.pem public.pem
```

### 4. Complete variable reference

| Variable | Required | Description | Example |
|---|---|---|---|
| `SECRET_KEY` | ✅ | Django secret key (50+ random chars) | *(generated above)* |
| `DEBUG` | ✅ | `False` in production, `True` for local dev | `False` |
| `ALLOWED_HOSTS` | ✅ | Comma-separated hostnames Django will serve | `localhost,tendershield.example.com` |
| `DB_ROOT_PASSWORD` | ✅ | MySQL root password | `s3cur3r00t!` |
| `DB_NAME` | ✅ | Database name | `tendershield` |
| `DB_USER` | ✅ | Application DB username | `tendershield` |
| `DB_PASSWORD` | ✅ | Application DB password | `s3cur3db!` |
| `DB_HOST` | ✅ | DB hostname (use `db` inside Docker Compose) | `db` |
| `DB_PORT` | ✅ | DB port | `3306` |
| `JWT_PRIVATE_KEY` | ✅ | RS256 private key (PEM, `\n`-escaped) | *(generated above)* |
| `JWT_PUBLIC_KEY` | ✅ | RS256 public key (PEM, `\n`-escaped) | *(generated above)* |
| `JWT_ACCESS_TOKEN_LIFETIME` | ✅ | Access token TTL in seconds (900–86400) | `3600` |
| `JWT_REFRESH_TOKEN_LIFETIME` | — | Refresh token TTL in seconds | `604800` |
| `REDIS_URL` | ✅ | Redis connection URL | `redis://redis:6379/0` |
| `CELERY_BROKER_URL` | ✅ | Celery broker URL | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | ✅ | Celery result backend URL | `redis://redis:6379/1` |
| `FRONTEND_ORIGIN` | ✅ | Allowed CORS origin for the frontend | `https://tendershield.example.com` |
| `NEXT_PUBLIC_API_URL` | ✅ | Backend API URL visible to the browser | `https://tendershield.example.com` |
| `EMAIL_HOST` | ✅ | SMTP server hostname | `smtp.example.com` |
| `EMAIL_PORT` | ✅ | SMTP port | `587` |
| `EMAIL_USE_TLS` | ✅ | Enable STARTTLS | `True` |
| `EMAIL_HOST_USER` | ✅ | SMTP username | `alerts@example.com` |
| `EMAIL_HOST_PASSWORD` | ✅ | SMTP password | *(secret)* |
| `DEFAULT_FROM_EMAIL` | — | Sender address for alert emails | `TenderShield Alerts <alerts@example.com>` |
| `ML_RETRAIN_INTERVAL_HOURS` | — | Hours between scheduled retraining (min 24) | `24` |
| `ML_IF_CONTAMINATION` | — | Isolation Forest contamination parameter | `0.05` |
| `ML_MODEL_PATH` | — | Path for serialized model artifacts | `/app/ml_worker/models` |
| `ALERT_DEFAULT_THRESHOLD` | — | Default fraud score alert threshold (0–100) | `70` |

---

## Database Migration Steps

### First-time setup

```bash
# 1. Start only the database service and wait for it to be healthy
docker compose up -d db
docker compose ps db   # wait until Health shows "healthy"

# 2. Apply all Django migrations
docker compose run --rm backend python manage.py migrate

# 3. Start the full stack
docker compose up -d
```

### Applying migrations on subsequent deployments

Always run migrations **before** routing traffic to a new backend container version (see `docs/deployment.md` for the full zero-downtime procedure):

```bash
docker compose run --rm backend python manage.py migrate --no-input
```

### Checking migration status

```bash
docker compose run --rm backend python manage.py showmigrations
```

---

## Initial Admin User Creation

After the first migration, create the initial administrator account using the built-in management command:

```bash
docker compose run --rm backend \
  python manage.py create_superuser_admin \
  --username admin \
  --email admin@example.com \
  --password "ChangeMe123!"
```

> **Security note:** Change the password immediately after first login via the TenderShield web UI or the Django admin panel at `/admin/`. The account is automatically locked after 5 consecutive failed login attempts within 10 minutes.

The `create_superuser_admin` command creates a user with the `ADMIN` role, which grants full read-write access to all API endpoints and the Django admin panel.

---

## ML Model Training Invocation

The ML worker requires trained model artifacts before it can produce anomaly and collusion scores. On a fresh deployment, no models exist yet — the system will operate in rule-only mode (ML scores will be `null`) until training completes.

### Trigger initial training manually

```bash
# Ensure the ml-worker service is running
docker compose up -d ml-worker

# Trigger a one-off retraining task via Celery
docker compose run --rm ml-worker \
  python -c "
from ml_worker.tasks import retrain_models
result = retrain_models.apply()
print(result.get())
"
```

Expected output when sufficient data is available:

```json
{
  "status": "ok",
  "isolation_forest_version": "IF-20260101T120000",
  "random_forest_version": "RF-20260101T120000",
  "samples": 150
}
```

If fewer than 10 labeled tender records exist, training is skipped:

```json
{"status": "skipped", "reason": "insufficient_data", "samples": 3}
```

Ingest at least 10 tender records with bids before triggering training.

### Scheduled retraining

Celery Beat automatically retrains models at the interval set by `ML_RETRAIN_INTERVAL_HOURS` (default: 24 hours, minimum enforced: 24 hours per Requirement 4.4). No manual action is required after the initial training run.

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

## PDF Export Setup

TenderShield generates PDF audit log exports using `reportlab`. No additional installation is required — `reportlab` is included in `backend/requirements.txt`.

### How PDF export works

1. An Administrator sends `POST /api/v1/audit-log/export/` with a date range:

   ```bash
   curl -X POST http://localhost:8000/api/v1/audit-log/export/ \
     -H "Authorization: Bearer <admin-jwt>" \
     -H "Content-Type: application/json" \
     -d '{"date_from": "2026-01-01", "date_to": "2026-12-31"}'
   ```

   Response: `{"task_id": "abc123", "status": "queued"}`

2. Poll for completion:

   ```bash
   curl http://localhost:8000/api/v1/audit-log/export/abc123/status/ \
     -H "Authorization: Bearer <admin-jwt>"
   ```

   Response when complete: `{"status": "complete", "download_url": "/media/exports/audit_2026-01-01_2026-12-31.pdf"}`

3. Download the PDF:

   ```bash
   curl -O http://localhost:8000/media/exports/audit_2026-01-01_2026-12-31.pdf \
     -H "Authorization: Bearer <admin-jwt>"
   ```

### Storage configuration

PDF exports are written to `MEDIA_ROOT` (default: `backend/media/`). Ensure the backend container has write access to this directory. In Docker Compose, the `./backend` volume mount covers this automatically.

For production, consider mounting a persistent volume or an object storage bucket at `MEDIA_ROOT` to prevent export files from being lost on container restarts.

### Retention

PDF exports are not automatically deleted. Implement a cron job or object storage lifecycle policy to remove exports older than your retention policy requires.

---

## Verifying the Installation

Once the full stack is running, verify all services are healthy:

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```

Expected response (HTTP 200):

```json
{
  "status": "ok",
  "db": "ok",
  "redis": "ok",
  "ml_worker": "ok"
}
```

If any service is unreachable, the response will be HTTP 503 with `"status": "degraded"` and the failing service(s) marked as `"error"`. See `docs/deployment.md` for troubleshooting steps.
