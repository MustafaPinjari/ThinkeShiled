from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone


class RiskStatus(models.TextChoices):
    LOW = "LOW", "Low Risk"
    MEDIUM = "MEDIUM", "Medium Risk"
    HIGH_RISK = "HIGH_RISK", "High Risk"


class CompanyProfile(models.Model):
    bidder = models.OneToOneField(
        "bids.Bidder", on_delete=models.CASCADE, related_name="company_profile"
    )
    total_bids = models.PositiveIntegerField(default=0)
    total_wins = models.PositiveIntegerField(default=0)
    win_rate = models.DecimalField(max_digits=5, decimal_places=4, default=0)  # 0.0000–1.0000
    avg_bid_deviation = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    active_red_flag_count = models.PositiveIntegerField(default=0)
    highest_fraud_risk_score = models.PositiveSmallIntegerField(default=0)
    risk_status = models.CharField(max_length=10, choices=RiskStatus.choices, default=RiskStatus.LOW)
    collusion_ring = models.ForeignKey(
        "graph.CollusionRing",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="company_profiles",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "companies_companyprofile"
        indexes = [
            models.Index(fields=["risk_status"]),
        ]

    def __str__(self):
        return f"Profile for {self.bidder} ({self.risk_status})"

    def delete(self, *args, **kwargs):
        """
        Block hard-deletes to satisfy the 5-year retention policy (Requirement 7.6).
        CompanyProfile records must never be permanently removed.
        """
        raise PermissionDenied(
            "CompanyProfile records cannot be deleted. "
            "Retention policy requires a minimum of 5 years."
        )
