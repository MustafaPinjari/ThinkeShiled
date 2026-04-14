"""
GET /health — service health check endpoint.

Returns HTTP 200 with {"status": "ok", ...} when all dependent services
are reachable, or HTTP 503 with {"status": "degraded", ...} when any
service is unreachable.

Checked services:
  - db       : Django ORM connection (SELECT 1)
  - redis    : Redis PING via django.core.cache
  - ml_worker: Celery worker ping (inspect ping with 2 s timeout)
"""

from __future__ import annotations

import logging

from django.http import JsonResponse
from django.views import View

logger = logging.getLogger(__name__)


def _check_db() -> str:
    try:
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return "ok"
    except Exception as exc:
        logger.warning("Health check: DB unreachable — %s", exc)
        return "error"


def _check_redis() -> str:
    try:
        from django.core.cache import cache

        cache.set("_health_ping", "1", timeout=5)
        val = cache.get("_health_ping")
        return "ok" if val == "1" else "error"
    except Exception as exc:
        logger.warning("Health check: Redis unreachable — %s", exc)
        return "error"


def _check_ml_worker() -> str:
    try:
        from config.celery import app as celery_app

        inspector = celery_app.control.inspect(timeout=2)
        ping_result = inspector.ping()
        # ping_result is None or an empty dict when no workers respond
        if ping_result:
            return "ok"
        return "error"
    except Exception as exc:
        logger.warning("Health check: ML worker unreachable — %s", exc)
        return "error"


class HealthView(View):
    """Health check endpoint — no authentication required."""

    def get(self, request):
        db_status = _check_db()
        redis_status = _check_redis()
        ml_worker_status = _check_ml_worker()

        all_ok = all(s == "ok" for s in (db_status, redis_status, ml_worker_status))

        payload = {
            "status": "ok" if all_ok else "degraded",
            "db": db_status,
            "redis": redis_status,
            "ml_worker": ml_worker_status,
        }
        http_status = 200 if all_ok else 503
        return JsonResponse(payload, status=http_status)
