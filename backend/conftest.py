"""
conftest.py — pytest configuration for TenderShield backend tests.

Ensures database connections have all required settings keys populated.
"""
import pytest


@pytest.fixture(autouse=True)
def ensure_db_settings_defaults():
    """
    Ensure all database connection settings have required keys like
    ATOMIC_REQUESTS. This is needed because pytest-django may create
    connection handlers with minimal settings dicts.
    """
    from django.db import connections
    for alias in connections:
        conn = connections[alias]
        conn.settings_dict.setdefault("ATOMIC_REQUESTS", False)
        conn.settings_dict.setdefault("AUTOCOMMIT", True)
        conn.settings_dict.setdefault("CONN_MAX_AGE", 0)
        conn.settings_dict.setdefault("CONN_HEALTH_CHECKS", False)
        conn.settings_dict.setdefault("OPTIONS", {})
        conn.settings_dict.setdefault("TIME_ZONE", None)
        conn.settings_dict.setdefault("TEST", {})
    yield
