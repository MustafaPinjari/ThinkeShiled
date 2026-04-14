# Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
#
# For any event of the specified types, an AuditLog entry is created with all
# required fields (event_type, timestamp UTC, user_id, affected_entity_type,
# affected_entity_id, data_snapshot). For any existing AuditLog entry, any
# attempt to update or delete it raises PermissionDenied.
# Validates: Requirements 11.1, 11.2, 11.3

import dataclasses
from typing import Optional

from django.core.exceptions import PermissionDenied
from django.utils import timezone
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

from audit.models import AuditLog, EventType
from audit.utils import write_audit_log
from authentication.models import User, UserRole

# ---------------------------------------------------------------------------
# Event types required by Requirement 11.1
# ---------------------------------------------------------------------------

EVENT_TYPES = [
    EventType.USER_LOGIN,
    EventType.USER_LOGOUT,
    EventType.TENDER_INGESTED,
    EventType.BID_INGESTED,
    EventType.SCORE_COMPUTED,
    EventType.RED_FLAG_RAISED,
    EventType.RED_FLAG_CLEARED,
    EventType.ALERT_SENT,
    EventType.STATUS_CHANGED,
]

# ---------------------------------------------------------------------------
# AuditEvent dataclass — the strategy builds instances of this
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class AuditEvent:
    event_type: str
    entity_type: str
    entity_id: str
    data_snapshot: dict
    ip_address: Optional[str]


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

_entity_type_st = st.sampled_from([
    "User", "Tender", "Bid", "RedFlag", "FraudRiskScore", "Alert",
])

_entity_id_st = st.one_of(
    st.integers(min_value=1, max_value=999999).map(str),
    st.text(min_size=1, max_size=20, alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"),
)

_snapshot_st = st.fixed_dictionaries({}).flatmap(
    lambda _: st.dictionaries(
        keys=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz_"),
        values=st.one_of(st.integers(), st.text(max_size=50), st.booleans()),
        max_size=5,
    )
)

_ip_st = st.one_of(
    st.none(),
    st.just("127.0.0.1"),
    st.just("192.168.1.100"),
    st.just("10.0.0.1"),
    st.just("::1"),
)

_audit_event_st = st.builds(
    AuditEvent,
    event_type=st.sampled_from(EVENT_TYPES),
    entity_type=_entity_type_st,
    entity_id=_entity_id_st,
    data_snapshot=_snapshot_st,
    ip_address=_ip_st,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_counter = 0


def _uid():
    global _counter
    _counter += 1
    return _counter


def _make_user():
    uid = _uid()
    return User.objects.create_user(
        username=f"pbt-audit-{uid}",
        email=f"pbt-audit-{uid}@test.com",
        password="testpass",
        role=UserRole.ADMIN,
    )


# ---------------------------------------------------------------------------
# Property 18a — Audit Log Completeness
# For any event of the specified types, write_audit_log() creates an AuditLog
# entry with all required fields populated correctly.
# Validates: Requirements 11.1, 11.2
# ---------------------------------------------------------------------------

class AuditLogCompletenessTest(TestCase):
    """
    Property 18: Audit Log Completeness.
    Validates: Requirements 11.1, 11.2
    """

    @given(event=_audit_event_st)
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_audit_log_entry_created_with_all_required_fields(self, event):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        user = _make_user()

        before = timezone.now()
        log = write_audit_log(
            event_type=event.event_type,
            user=user,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            data_snapshot=event.data_snapshot,
            ip_address=event.ip_address,
        )
        after = timezone.now()

        # Entry must be created (not None)
        assert log is not None, (
            f"write_audit_log returned None for event_type={event.event_type}"
        )
        assert log.pk is not None, "AuditLog entry must be persisted (pk must be set)"

        # Req 11.2: event_type must match
        assert log.event_type == event.event_type, (
            f"Expected event_type={event.event_type}, got {log.event_type}"
        )

        # Req 11.2: timestamp must be UTC and within the test window
        assert log.timestamp is not None, "timestamp must not be None"
        assert log.timestamp.tzinfo is not None, "timestamp must be timezone-aware (UTC)"
        assert before <= log.timestamp <= after, (
            f"timestamp {log.timestamp} is outside the expected window [{before}, {after}]"
        )

        # Req 11.2: user_id must be recorded
        assert log.user_id == user.pk, (
            f"Expected user_id={user.pk}, got {log.user_id}"
        )

        # Req 11.2: affected_entity_type and affected_entity_id must be stored
        assert log.affected_entity_type == event.entity_type, (
            f"Expected entity_type={event.entity_type!r}, got {log.affected_entity_type!r}"
        )
        assert log.affected_entity_id == event.entity_id, (
            f"Expected entity_id={event.entity_id!r}, got {log.affected_entity_id!r}"
        )

        # Req 11.2: data_snapshot must be stored as a JSON-serialisable dict
        assert isinstance(log.data_snapshot, dict), (
            f"data_snapshot must be a dict, got {type(log.data_snapshot)}"
        )
        assert log.data_snapshot == event.data_snapshot, (
            "data_snapshot content must match what was passed to write_audit_log"
        )

    @given(event_type=st.sampled_from(EVENT_TYPES))
    @settings(max_examples=len(EVENT_TYPES), suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_every_required_event_type_is_accepted(self, event_type):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        # Req 11.1: all specified event types must produce a persisted entry
        user = _make_user()
        log = write_audit_log(
            event_type=event_type,
            user=user,
            entity_type="Test",
            entity_id="1",
            data_snapshot={"event": event_type},
        )
        assert log is not None, f"write_audit_log must succeed for event_type={event_type}"
        assert log.pk is not None, f"Entry for event_type={event_type} must be persisted"
        assert log.event_type == event_type

    @given(event=_audit_event_st)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_system_event_without_user_stores_null_user(self, event):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        # System-generated events (e.g. SCORE_COMPUTED) may have user=None
        log = write_audit_log(
            event_type=event.event_type,
            user=None,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            data_snapshot=event.data_snapshot,
        )
        assert log is not None
        assert log.user_id is None, (
            "user_id must be None for system-generated events with no user"
        )
        # All other required fields must still be present
        assert log.event_type == event.event_type
        assert log.timestamp is not None
        assert log.timestamp.tzinfo is not None

    @given(
        event_type=st.sampled_from(EVENT_TYPES),
        ip=st.sampled_from(["127.0.0.1", "10.0.0.1", "192.168.0.1", "::1", None]),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_ip_address_stored_correctly(self, event_type, ip):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        user = _make_user()
        log = write_audit_log(
            event_type=event_type,
            user=user,
            entity_type="User",
            entity_id=str(user.pk),
            ip_address=ip,
        )
        assert log is not None
        assert log.ip_address == ip, (
            f"Expected ip_address={ip!r}, got {log.ip_address!r}"
        )


# ---------------------------------------------------------------------------
# Property 18b — Audit Log Immutability
# For any existing AuditLog entry, any attempt to update or delete it raises
# PermissionDenied.
# Validates: Requirement 11.3
# ---------------------------------------------------------------------------

class AuditLogImmutabilityTest(TestCase):
    """
    Property 18: Audit Log Immutability.
    Validates: Requirement 11.3
    """

    @given(event=_audit_event_st)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_update_raises_permission_denied(self, event):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        user = _make_user()
        log = write_audit_log(
            event_type=event.event_type,
            user=user,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            data_snapshot=event.data_snapshot,
        )
        assert log is not None and log.pk is not None

        # Any field mutation followed by save() must raise PermissionDenied
        log.data_snapshot = {"tampered": True}
        try:
            log.save()
            assert False, (
                f"Expected PermissionDenied when updating AuditLog pk={log.pk}, "
                f"but save() succeeded — immutability is broken"
            )
        except PermissionDenied:
            pass  # correct behaviour

    @given(event=_audit_event_st)
    @settings(max_examples=30, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_delete_raises_permission_denied(self, event):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        user = _make_user()
        log = write_audit_log(
            event_type=event.event_type,
            user=user,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            data_snapshot=event.data_snapshot,
        )
        assert log is not None and log.pk is not None

        try:
            log.delete()
            assert False, (
                f"Expected PermissionDenied when deleting AuditLog pk={log.pk}, "
                f"but delete() succeeded — immutability is broken"
            )
        except PermissionDenied:
            pass  # correct behaviour

    @given(event=_audit_event_st)
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_entry_still_exists_after_failed_update(self, event):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        # After a blocked update attempt, the original entry must remain intact
        user = _make_user()
        original_snapshot = dict(event.data_snapshot)
        log = write_audit_log(
            event_type=event.event_type,
            user=user,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            data_snapshot=original_snapshot,
        )
        assert log is not None
        pk = log.pk

        # Attempt (and expect failure of) an update
        log.data_snapshot = {"tampered": True}
        try:
            log.save()
        except PermissionDenied:
            pass

        # Original entry must still exist with original data
        refreshed = AuditLog.objects.get(pk=pk)
        assert refreshed.data_snapshot == original_snapshot, (
            "Original data_snapshot must be unchanged after a blocked update attempt"
        )
        assert refreshed.event_type == event.event_type

    @given(event=_audit_event_st)
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_entry_still_exists_after_failed_delete(self, event):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        # After a blocked delete attempt, the entry must still be queryable
        user = _make_user()
        log = write_audit_log(
            event_type=event.event_type,
            user=user,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            data_snapshot=event.data_snapshot,
        )
        assert log is not None
        pk = log.pk

        try:
            log.delete()
        except PermissionDenied:
            pass

        assert AuditLog.objects.filter(pk=pk).exists(), (
            f"AuditLog entry pk={pk} must still exist after a blocked delete attempt"
        )

    @given(
        event_type=st.sampled_from(EVENT_TYPES),
        field_name=st.sampled_from(["event_type", "affected_entity_type", "affected_entity_id"]),
        new_value=st.text(min_size=1, max_size=20, alphabet="abcdefghijklmnopqrstuvwxyz"),
    )
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_any_field_mutation_raises_permission_denied(self, event_type, field_name, new_value):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        # Mutating any field and calling save() must raise PermissionDenied
        user = _make_user()
        log = write_audit_log(
            event_type=event_type,
            user=user,
            entity_type="Test",
            entity_id="1",
            data_snapshot={},
        )
        assert log is not None

        setattr(log, field_name, new_value)
        try:
            log.save()
            assert False, (
                f"Expected PermissionDenied when mutating field {field_name!r} "
                f"on AuditLog pk={log.pk}"
            )
        except PermissionDenied:
            pass  # correct behaviour

    @given(event=_audit_event_st)
    @settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow], deadline=None)
    def test_save_with_update_fields_still_raises(self, event):
        # Feature: tender-shield, Property 18: Audit Log Completeness and Immutability
        # Even save(update_fields=[...]) must not bypass the immutability guard
        user = _make_user()
        log = write_audit_log(
            event_type=event.event_type,
            user=user,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            data_snapshot=event.data_snapshot,
        )
        assert log is not None

        log.data_snapshot = {"bypass_attempt": True}
        try:
            log.save(update_fields=["data_snapshot"])
            assert False, (
                "Expected PermissionDenied when calling save(update_fields=...) "
                f"on AuditLog pk={log.pk}"
            )
        except PermissionDenied:
            pass  # correct behaviour
