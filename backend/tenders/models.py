from django.db import models
from django.utils import timezone


class TenderStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    CLOSED = "CLOSED", "Closed"
    AWARDED = "AWARDED", "Awarded"
    CANCELLED = "CANCELLED", "Cancelled"


class Tender(models.Model):
    tender_id = models.CharField(max_length=255, unique=True)
    title = models.CharField(max_length=500)
    category = models.CharField(max_length=255)
    estimated_value = models.DecimalField(max_digits=20, decimal_places=2)
    currency = models.CharField(max_length=10, default="INR")
    submission_deadline = models.DateTimeField()
    buyer_id = models.CharField(max_length=255)
    buyer_name = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=TenderStatus.choices, default=TenderStatus.ACTIVE)
    publication_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenders_tender"
        indexes = [
            models.Index(fields=["category"]),
            models.Index(fields=["buyer_name"]),
            models.Index(fields=["submission_deadline"]),
            models.Index(fields=["status"]),
        ]

    def __str__(self):
        return f"{self.tender_id}: {self.title}"
