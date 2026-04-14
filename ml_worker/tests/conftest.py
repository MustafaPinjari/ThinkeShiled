"""
pytest configuration for ml_worker unit tests.

Configures Django with minimal settings so that ml_worker.tasks can be
imported without a full Django project on sys.path.  All ORM calls in
the tasks are mocked in the individual tests.
"""

import django
from django.conf import settings


def pytest_configure(config):
    """Configure Django before any tests run."""
    if not settings.configured:
        settings.configure(
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
            ],
            USE_TZ=True,
            TIME_ZONE="UTC",
            # Minimal Celery config so shared_task decorator works
            CELERY_TASK_ALWAYS_EAGER=True,
            CELERY_TASK_EAGER_PROPAGATES=True,
        )
