"""
Audit logging utility.

Provides a single write_audit_log() helper that all event handlers call
to create immutable AuditLog entries.

Usage:
    from audit.utils import write_audit_log
    from audit.models import EventType

    write_audit_log(
        event_type=EventType.USER_LOGIN,
        user=request.user,
        entity_type="User",
        entity_id=str(request.user.id),
        data_snapshot={"username": request.user.username},
        ip_address=ip,
    )
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def write_audit_log(
    event_type: str,
    user=None,
    entity_type: str = "",
    entity_id: str = "",
    data_snapshot: Optional[dict] = None,
    ip_address: Optional[str] = None,
):
    """
    Create an immutable AuditLog entry.

    Parameters
    ----------
    event_type:     One of the EventType choices defined in audit.models.
    user:           The User instance responsible for the event (may be None
                    for system-generated events).
    entity_type:    Human-readable name of the affected model (e.g. "Tender").
    entity_id:      String representation of the affected record's PK.
    data_snapshot:  Arbitrary JSON-serialisable dict capturing the relevant
                    state at the time of the event.
    ip_address:     Client IP address (IPv4 or IPv6), or None.

    Returns the created AuditLog instance, or None if creation fails.
    """
    from audit.models import AuditLog

    try:
        return AuditLog.objects.create(
            event_type=event_type,
            user=user,
            affected_entity_type=entity_type,
            affected_entity_id=entity_id,
            data_snapshot=data_snapshot or {},
            ip_address=ip_address or None,
        )
    except Exception:
        # Never let audit logging break the calling code path.
        logger.exception(
            "Failed to write AuditLog entry: event_type=%s entity=%s/%s",
            event_type,
            entity_type,
            entity_id,
        )
        return None
