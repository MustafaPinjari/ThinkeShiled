from django.conf import settings
from django.db import models
from django.utils import timezone


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    DELIVERED = "DELIVERED", "Delivered"
    FAILED = "FAILED", "Failed"
    RETRYING = "RETRYING", "Retrying"
    PERMANENTLY_FAILED = "PERMANENTLY_FAILED", "Permanently Failed"


class AlertType(models.TextChoices):
    HIGH_RISK_SCORE = "HIGH_RISK_SCORE", "High Risk Score"
    COLLUSION_RING = "COLLUSION_RING", "Collusion Ring Detected"
    RED_FLAG = "RED_FLAG", "Red Flag Raised"


class Alert(models.Model):
    tender = models.ForeignKey(
        "tenders.Tender", on_delete=models.CASCADE, related_name="alerts"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alerts"
    )
    alert_type = models.CharField(max_length=30, choices=AlertType.choices, default=AlertType.HIGH_RISK_SCORE)
    title = models.CharField(max_length=500, blank=True, default="")
    detail_link = models.CharField(max_length=500, blank=True, default="")
    fraud_risk_score = models.PositiveSmallIntegerField()
    top_red_flags = models.JSONField(default=list)
    delivery_status = models.CharField(
        max_length=20, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    retry_count = models.PositiveSmallIntegerField(default=0)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "alerts_alert"
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["delivery_status"]),
            models.Index(fields=["tender"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Alert for Tender {self.tender_id} → User {self.user_id} ({self.delivery_status})"


class AlertSettings(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="alert_settings"
    )
    threshold = models.PositiveSmallIntegerField(default=70)
    category = models.CharField(max_length=255, blank=True, default="")  # empty = global
    email_enabled = models.BooleanField(default=True)

    class Meta:
        db_table = "alerts_alertsettings"
        unique_together = [("user", "category")]

    def __str__(self):
        cat = self.category or "global"
        return f"AlertSettings for {self.user} [{cat}] threshold={self.threshold}"
