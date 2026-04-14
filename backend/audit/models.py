from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone


class EventType(models.TextChoices):
    USER_LOGIN = "USER_LOGIN", "User Login"
    USER_LOGOUT = "USER_LOGOUT", "User Logout"
    USER_LOGIN_FAILED = "USER_LOGIN_FAILED", "User Login Failed"
    USER_LOCKED = "USER_LOCKED", "User Account Locked"
    TENDER_INGESTED = "TENDER_INGESTED", "Tender Ingested"
    BID_INGESTED = "BID_INGESTED", "Bid Ingested"
    SCORE_COMPUTED = "SCORE_COMPUTED", "Score Computed"
    RED_FLAG_RAISED = "RED_FLAG_RAISED", "Red Flag Raised"
    RED_FLAG_CLEARED = "RED_FLAG_CLEARED", "Red Flag Cleared"
    ALERT_SENT = "ALERT_SENT", "Alert Sent"
    ALERT_FAILED = "ALERT_FAILED", "Alert Delivery Failed"
    STATUS_CHANGED = "STATUS_CHANGED", "Status Changed"
    MODEL_RETRAINED = "MODEL_RETRAINED", "ML Model Retrained"
    SHAP_FAILED = "SHAP_FAILED", "SHAP Computation Failed"
    JWT_INVALID_KEY = "JWT_INVALID_KEY", "JWT Invalid Signing Key"
    EXPORT_GENERATED = "EXPORT_GENERATED", "Audit Export Generated"
    RULE_ADDED = "RULE_ADDED", "Rule Definition Added"
    EXPLANATION_GENERATED = "EXPLANATION_GENERATED", "Explanation Generated"


class AuditLog(models.Model):
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    timestamp = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
    )
    affected_entity_type = models.CharField(max_length=100, blank=True, default="")
    affected_entity_id = models.CharField(max_length=255, blank=True, default="")
    data_snapshot = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "audit_auditlog"
        indexes = [
            models.Index(fields=["event_type"]),
            models.Index(fields=["timestamp"]),
            models.Index(fields=["user"]),
            models.Index(fields=["affected_entity_type", "affected_entity_id"]),
        ]
        ordering = ["-timestamp"]

    def __str__(self):
        return f"[{self.timestamp}] {self.event_type} by user {self.user_id}"

    def save(self, *args, **kwargs):
        # Block updates — AuditLog entries are insert-only.
        #
        # MySQL INSERT-only constraint (Requirement 11.3):
        #   The MySQL user used by Django should have INSERT-only privileges on
        #   the audit_auditlog table.  Run the following after initial migration:
        #
        #     REVOKE UPDATE, DELETE ON tendershield.audit_auditlog FROM 'tendershield'@'%';
        #     FLUSH PRIVILEGES;
        #
        # 7-year retention policy (Requirement 11.5):
        #   AuditLog entries MUST NOT be hard-deleted.  Retention is enforced by:
        #   1. This delete() override (raises PermissionDenied for all callers).
        #   2. The MySQL user having no DELETE privilege on audit_auditlog.
        #   3. A scheduled database backup policy retaining backups for ≥ 7 years.
        #   See docs/setup.md for the full retention and backup procedure.
        if self.pk is not None:
            raise PermissionDenied("AuditLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Hard-delete is permanently prohibited to satisfy the 7-year retention
        # requirement (Requirement 11.5) and tamper-evidence requirement (11.3).
        raise PermissionDenied("AuditLog entries cannot be deleted.")