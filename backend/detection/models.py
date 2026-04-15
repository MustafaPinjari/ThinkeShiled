from django.db import models
from django.utils import timezone


class FlagType(models.TextChoices):
    SINGLE_BIDDER = "SINGLE_BIDDER", "Single Bidder"
    PRICE_ANOMALY = "PRICE_ANOMALY", "Price Anomaly"
    REPEAT_WINNER = "REPEAT_WINNER", "Repeat Winner"
    SHORT_DEADLINE = "SHORT_DEADLINE", "Short Deadline"
    LINKED_ENTITIES = "LINKED_ENTITIES", "Linked Entities"
    COVER_BID_PATTERN = "COVER_BID_PATTERN", "Cover Bid Pattern"
    SPEC_TAILORING = "SPEC_TAILORING", "Specification Tailoring"
    SPEC_COPY_PASTE = "SPEC_COPY_PASTE", "Copy-Paste Fraud"
    SPEC_VAGUE_SCOPE = "SPEC_VAGUE_SCOPE", "Vague Scope"
    SPEC_UNUSUAL_RESTRICTION = "SPEC_UNUSUAL_RESTRICTION", "Unusual Restriction"


class Severity(models.TextChoices):
    LOW = "LOW", "Low"
    MEDIUM = "MEDIUM", "Medium"
    HIGH = "HIGH", "High"


class RuleDefinition(models.Model):
    rule_code = models.CharField(max_length=100, unique=True)
    description = models.TextField()
    severity = models.CharField(max_length=10, choices=Severity.choices)
    is_active = models.BooleanField(default=True)
    parameters = models.JSONField(default=dict)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "detection_ruledefinition"

    def __str__(self):
        return f"{self.rule_code} ({self.severity})"


class RedFlag(models.Model):
    tender = models.ForeignKey(
        "tenders.Tender", on_delete=models.CASCADE, related_name="red_flags"
    )
    bidder = models.ForeignKey(
        "bids.Bidder", on_delete=models.SET_NULL, null=True, blank=True, related_name="red_flags"
    )
    flag_type = models.CharField(max_length=50, choices=FlagType.choices)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    rule_version = models.CharField(max_length=50, default="1.0")
    trigger_data = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)
    raised_at = models.DateTimeField(default=timezone.now)
    cleared_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "detection_redflag"
        indexes = [
            models.Index(fields=["tender", "is_active"]),
            models.Index(fields=["flag_type"]),
            models.Index(fields=["severity"]),
        ]

    def __str__(self):
        return f"{self.flag_type} ({self.severity}) on Tender {self.tender_id}"

    def clear(self):
        self.is_active = False
        self.cleared_at = timezone.now()
        self.save(update_fields=["is_active", "cleared_at"])
