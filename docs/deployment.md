# TenderShield — Deployment Guide

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Variables](#environment-variables)
3. [Database Migration Steps](#database-migration-steps)
4. [Initial Admin User Creation](#initial-admin-user-creation)
5. [ML Model Training](#ml-model-training)
6. [Zero-Downtime Deployment Strategy](#zero-downtime-deployment-strategy)
7. [CI/CD Pipeline Overview](#cicd-pipeline-overview)
8. [Audit Log Retention](#audit-log-retention)
9. [Troubleshooting](#troubleshooting)

---

## Prerequisites

- Docker ≥ 24 and Docker Compose v2 (`docker compose` command)
- `openssl` (for generating RS256 JWT key pair)
- Access to a container registry (default: GitHub Container Registry — `ghcr.io`)

---

## Docker Compose Startup

### Start the full stack

```bash
# Copy and configure environment variables first (see docs/setup.md)
cp .env.example .env
# ... fill in .env values ...

# Start all services in detached mode
docker compose up -d
```

All five services start in dependency order: `db` → `redis` → `backend` + `ml-worker` → `frontend`. Health checks ensure each service is ready before dependents start.

### Verify all services are healthy

```bash
docker compose ps
```

All services should show `healthy` within 60 seconds. Then confirm the backend is responding:

```bash
curl -s http://localhost:8000/health | python3 -m json.tool
# Expected: {"status": "ok", "db": "ok", "redis": "ok", "ml_worker": "ok"}
```

### Stop the stack

```bash
docker compose down          # stop containers, keep volumes
docker compose down -v       # stop containers and remove volumes (destructive)
```

### View logs

```bash
docker compose logs -f backend    # follow backend logs
docker compose logs --tail=50     # last 50 lines from all services
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in every value before starting the stack:

```bash
cp .env.example .env
```

### Generating the RS256 JWT Key Pair

```bash
openssl genrsa -out private.pem 2048
openssl rsa -in private.pem -pubout -out public.pem
```

Paste the PEM content into `.env`, replacing literal newlines with `\n`:

```bash
JWT_PRIVATE_KEY="$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' private.pem)"
JWT_PUBLIC_KEY="$(awk 'NF {sub(/\r/, ""); printf "%s\\n",$0;}' public.pem)"
```

Remove the `.pem` files from disk after copying the values.

### Key Variables Reference

| Variable | Description | Example |
|---|---|---|
| `SECRET_KEY` | Django secret key (50+ random chars) | `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` |
| `DB_ROOT_PASSWORD` | MySQL root password | `s3cur3r00t!` |
| `DB_NAME` | Database name | `tendershield` |
| `DB_USER` / `DB_PASSWORD` | Application DB credentials | — |
| `JWT_PRIVATE_KEY` | RS256 private key (PEM, `\n`-escaped) | — |
| `JWT_PUBLIC_KEY` | RS256 public key (PEM, `\n`-escaped) | — |
| `JWT_ACCESS_TOKEN_LIFETIME` | Access token TTL in seconds (900–86400) | `3600` |
| `REDIS_URL` | Redis connection URL | `redis://redis:6379/0` |
| `FRONTEND_ORIGIN` | Allowed CORS origin | `https://tendershield.example.com` |
| `EMAIL_HOST` | SMTP host for alert emails | `smtp.example.com` |
| `ALERT_DEFAULT_THRESHOLD` | Default fraud score alert threshold | `70` |

---

## Database Migration Steps

Migrations must be applied **before** routing traffic to a new backend container version. This is the core of the zero-downtime strategy (see [below](#zero-downtime-deployment-strategy)).

### First-time setup

```bash
# Start only the database service
docker compose up -d db

# Wait for MySQL to be healthy
docker compose ps db   # Health: healthy

# Run migrations via a one-off backend container
docker compose run --rm backend python manage.py migrate

# Start the rest of the stack
docker compose up -d
```

### Subsequent deployments

See the [Zero-Downtime Deployment Strategy](#zero-downtime-deployment-strategy) section — migrations are always run as a separate step before the backend container is replaced.

---

## Initial Admin User Creation

After the first migration, create the initial administrator account using the management command:

```bash
docker compose run --rm backend \
  python manage.py create_superuser_admin \
  --username admin \
  --email admin@example.com \
  --password "ChangeMe123!"
```

> **Security note:** Change the password immediately after first login. The account is locked after 5 consecutive failed login attempts within 10 minutes.

---

## ML Model Training

The ML worker requires trained model artifacts before it can produce anomaly and collusion scores. On a fresh deployment, trigger an initial training run:

```bash
# Ensure the ml-worker service is running
docker compose up -d ml-worker

# Trigger a one-off training task
docker compose run --rm ml-worker \
  python -c "from ml_worker.train import train_isolation_forest, train_random_forest; print('Training complete')"
```

Scheduled retraining runs automatically via Celery Beat at the interval configured by `ML_RETRAIN_INTERVAL_HOURS` (default: 24 hours). The minimum allowed interval is 24 hours (Requirement 4.4).

---

## Zero-Downtime Deployment Strategy

TenderShield uses a **migrate-then-swap** pattern to avoid downtime during backend updates. The key principle: **database migrations run before any new backend container starts serving traffic**.

### Why this matters

Django migrations are backward-compatible by design (additive changes only — new columns are nullable, old columns are removed in a follow-up release). This means:

- The **old** backend container can continue serving requests while migrations run.
- The **new** backend container starts only after migrations complete successfully.
- If migrations fail, the old container keeps running and no traffic is disrupted.

### Deployment procedure

```
┌─────────────────────────────────────────────────────────────────┐
│  Step 1: Pull new images (tagged with commit SHA)               │
│  Step 2: Run migrations via one-off container (new image)       │
│  Step 3: Replace backend container with new image               │
│  Step 4: Verify /health returns {"status": "ok"}                │
│  Step 5: Replace ml-worker container with new image             │
│  Step 6: Replace frontend container with new image              │
└─────────────────────────────────────────────────────────────────┘
```

### Step-by-step commands

```bash
# 1. Set the target image tag (commit SHA from CI)
export SHA=<commit-sha>
export REGISTRY=ghcr.io/<your-org>/tendershield

# 2. Pull new images
docker pull ${REGISTRY}-backend:${SHA}
docker pull ${REGISTRY}-ml-worker:${SHA}
docker pull ${REGISTRY}-frontend:${SHA}

# 3. Run migrations BEFORE swapping the backend container
#    The old backend continues serving traffic during this step.
docker run --rm \
  --env-file .env \
  --network tendershield_default \
  ${REGISTRY}-backend:${SHA} \
  python manage.py migrate --no-input

# 4. Swap the backend container (zero-downtime: old container handles
#    in-flight requests; new container starts accepting new requests)
docker compose up -d --no-deps --no-build \
  -e "BACKEND_IMAGE=${REGISTRY}-backend:${SHA}" backend

# 5. Verify health before proceeding
curl -sf http://localhost:8000/health | python3 -c \
  "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d['status']=='ok' else 1)"

# 6. Swap ml-worker and frontend
docker compose up -d --no-deps --no-build \
  -e "ML_WORKER_IMAGE=${REGISTRY}-ml-worker:${SHA}" ml-worker

docker compose up -d --no-deps --no-build \
  -e "FRONTEND_IMAGE=${REGISTRY}-frontend:${SHA}" frontend
```

### Rollback

If the health check fails after swapping the backend:

```bash
# Re-run the previous image (no migration rollback needed for additive changes)
docker compose up -d --no-deps --no-build \
  -e "BACKEND_IMAGE=${REGISTRY}-backend:<previous-sha>" backend
```

> **Note:** Destructive migrations (column drops, renames) must be split across two releases: release N adds the new column and keeps the old one; release N+1 removes the old column after all instances have migrated.

### Using Docker Compose override for image pinning

For production, use a `docker-compose.override.yml` to pin image tags:

```yaml
# docker-compose.override.yml (generated by CI, not committed)
services:
  backend:
    image: ghcr.io/<your-org>/tendershield-backend:<sha>
    build: ~   # disable build; use pre-built image
  ml-worker:
    image: ghcr.io/<your-org>/tendershield-ml-worker:<sha>
    build: ~
  frontend:
    image: ghcr.io/<your-org>/tendershield-frontend:<sha>
    build: ~
```

---

## CI/CD Pipeline Overview

The GitHub Actions workflow at `.github/workflows/ci.yml` runs on every push to `main`:

| Job | Trigger | What it does |
|---|---|---|
| `backend-tests` | push/PR | Runs `pytest` with SQLite in-memory DB (no external services needed) |
| `frontend-tests` | push/PR | Runs `jest --ci` |
| `build-backend` | after `backend-tests` passes | Builds and pushes `backend` image tagged with commit SHA |
| `build-ml-worker` | after `backend-tests` passes | Builds and pushes `ml-worker` image tagged with commit SHA |
| `build-frontend` | after `frontend-tests` passes | Builds and pushes `frontend` image tagged with commit SHA |
| `smoke-test` | after all builds pass (main only) | Starts full Docker Compose stack, waits ≤60 s for all health checks, hits `/health` |

Images are pushed to GitHub Container Registry (`ghcr.io`) and tagged with both the commit SHA and `latest`.

---

## Audit Log Retention

Per Requirement 11.5, audit log entries must be retained for a **minimum of 7 years**. The `AuditLog` model enforces immutability at the application layer (no UPDATE or DELETE). At the database layer, the MySQL user has INSERT-only permissions on the `audit_log` table.

To prevent accidental data loss:

- Do **not** run `python manage.py flush` in production.
- Do **not** grant `DELETE` or `UPDATE` on `audit_log` to the application DB user.
- Schedule regular MySQL backups with a retention policy of at least 7 years.

---

## Troubleshooting

### Services not healthy within 60 seconds

```bash
docker compose ps          # check health status
docker compose logs db     # MySQL startup errors
docker compose logs backend  # Django startup / migration errors
```

Common causes:
- MySQL not yet accepting connections — increase `start_period` in `docker-compose.yml` or wait longer.
- Missing `.env` values — ensure all variables from `.env.example` are set.
- JWT key format — ensure `\n` line endings are preserved in the PEM values.

### Backend returns 500 on `/health`

```bash
docker compose logs backend --tail=50
```

Check for:
- Database connection errors (wrong `DB_HOST`, `DB_PASSWORD`)
- Redis connection errors (wrong `REDIS_URL`)
- Missing Django migrations (`python manage.py showmigrations`)

### ML scores are null

This is expected on a fresh deployment before the first training run. Trigger training manually:

```bash
docker compose run --rm ml-worker \
  python -c "from ml_worker.tasks import retrain_models_task; retrain_models_task.apply()"
```
