"""
Django settings for TenderShield.
"""

import os
from datetime import timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-change-me-in-production")

DEBUG = os.environ.get("DEBUG", "False") == "True"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# ---------------------------------------------------------------------------
# Installed apps
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django built-ins
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_ratelimit",
    # TenderShield apps
    "authentication",
    "tenders",
    "bids",
    "detection",
    "scoring",
    "xai",
    "companies",
    "graph",
    "alerts",
    "audit",
    "nlp",
]

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database — MySQL 8
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": os.environ.get("DB_NAME", "tendershield"),
        "USER": os.environ.get("DB_USER", "tendershield"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "127.0.0.1"),
        "PORT": os.environ.get("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

# ---------------------------------------------------------------------------
# Cache — LocMemCache for local dev (no Redis, no file permissions issues)
# ---------------------------------------------------------------------------
REDIS_URL = os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")

def _redis_available(url: str) -> bool:
    try:
        import redis as _redis
        client = _redis.from_url(url, socket_connect_timeout=1)
        client.ping()
        return True
    except Exception:
        return False

if _redis_available(REDIS_URL):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "tendershield-dev",
        }
    }

# Silence ratelimit system check errors when Redis is unavailable in dev
SILENCED_SYSTEM_CHECKS = ["django_ratelimit.W001", "django_ratelimit.E003"]

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://redis:6379/1")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "UTC"

# ---------------------------------------------------------------------------
# Celery Beat — scheduled tasks
# ---------------------------------------------------------------------------
_retrain_interval_hours = int(os.environ.get("ML_RETRAIN_INTERVAL_HOURS", "24"))

CELERY_BEAT_SCHEDULE = {
    "retrain-ml-models": {
        "task": "ml_worker.retrain_models",
        # Run every ML_RETRAIN_INTERVAL_HOURS hours (minimum 24 h per Requirement 4.4)
        "schedule": max(_retrain_interval_hours, 24) * 3600,  # seconds
    },
    "retry-failed-alert-emails": {
        "task": "alerts.tasks.retry_failed_emails",
        "schedule": 300,  # every 5 minutes
    },
}

# ---------------------------------------------------------------------------
# Password hashers — bcrypt with cost ≥ 12
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

BCRYPT_ROUNDS = 12  # referenced by custom hasher config if needed

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "authentication.jwt_auth.AuditingJWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "EXCEPTION_HANDLER": "config.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": (
        "authentication.throttles.AuthenticatedUserThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "authenticated_user": "100/min",
    },
}

# ---------------------------------------------------------------------------
# Simple JWT — RS256
# ---------------------------------------------------------------------------
_jwt_private_key = os.environ.get("JWT_PRIVATE_KEY", "")
_jwt_public_key = os.environ.get("JWT_PUBLIC_KEY", "")

# Replace literal \n with actual newlines (common in env var storage)
if _jwt_private_key:
    _jwt_private_key = _jwt_private_key.replace("\\n", "\n")
if _jwt_public_key:
    _jwt_public_key = _jwt_public_key.replace("\\n", "\n")

_access_lifetime_seconds = int(os.environ.get("JWT_ACCESS_TOKEN_LIFETIME", "3600"))
_refresh_lifetime_seconds = int(os.environ.get("JWT_REFRESH_TOKEN_LIFETIME", "604800"))

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=_access_lifetime_seconds),
    "REFRESH_TOKEN_LIFETIME": timedelta(seconds=_refresh_lifetime_seconds),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "RS256",
    "SIGNING_KEY": _jwt_private_key or SECRET_KEY,  # fallback to SECRET_KEY in dev
    "VERIFYING_KEY": _jwt_public_key or None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_TYPE_CLAIM": "token_type",
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")
CORS_ALLOWED_ORIGINS = [FRONTEND_ORIGIN]
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# Security (task 2.4 — SSL redirect, HSTS, CORS)
# ---------------------------------------------------------------------------
SECURE_SSL_REDIRECT = not DEBUG  # True in production; False in local dev
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# ---------------------------------------------------------------------------
# Email (SMTP)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.example.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True") == "True"
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "TenderShield Alerts <alerts@example.com>")

# ---------------------------------------------------------------------------
# Alert defaults
# ---------------------------------------------------------------------------
ALERT_DEFAULT_THRESHOLD = int(os.environ.get("ALERT_DEFAULT_THRESHOLD", "70"))

# ---------------------------------------------------------------------------
# data.gov.in OGD API (GeM / CPPP real tender data)
# ---------------------------------------------------------------------------
DATAGOV_API_KEY = os.environ.get("DATAGOV_API_KEY", "")
DATAGOV_RESOURCE_ID = os.environ.get("DATAGOV_RESOURCE_ID", "")

# ---------------------------------------------------------------------------
# ML Worker settings
# ---------------------------------------------------------------------------
ML_RETRAIN_INTERVAL_HOURS = int(os.environ.get("ML_RETRAIN_INTERVAL_HOURS", "24"))
ML_IF_CONTAMINATION = float(os.environ.get("ML_IF_CONTAMINATION", "0.05"))
ML_MODEL_PATH = os.environ.get("ML_MODEL_PATH", str(BASE_DIR.parent / "ml_worker" / "models"))

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# ---------------------------------------------------------------------------
# Media files (audit PDF exports, etc.)
# ---------------------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Custom user model
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "authentication.User"

# ---------------------------------------------------------------------------
# Default primary key
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
