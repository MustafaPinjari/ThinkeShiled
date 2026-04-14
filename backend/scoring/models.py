from django.db import models
from django.utils import timezone


class ScoringWeightConfig(models.Model):
    """
    Administrator-configured weight overrides for the fraud risk scoring formula.

    Only one active config is used at a time (latest by created_at where is_active=True).
    """

    weights = models.JSONField(
        default=dict,
        help_text=(
            "Keys: high_weight, medium_weight, red_flag_cap, "
            "ml_anomaly_weight, ml_collusion_weight"
        ),
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(
        "authentication.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scoring_weight_configs",
    )

    class Meta:
        db_table = "scoring_weightconfig"
        ordering = ["-created_at"]

    def __str__(self):
        return f"ScoringWeightConfig (active={self.is_active}) created {self.created_at}"


class FraudRiskScore(models.Model):
    tender = models.ForeignKey(
        "tenders.Tender", on_delete=models.CASCADE, related_name="fraud_risk_scores"
    )
    score = models.PositiveSmallIntegerField()  # integer [0, 100]
    ml_anomaly_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    ml_collusion_score = models.DecimalField(max_digits=5, decimal_places=4, null=True, blank=True)
    red_flag_contribution = models.PositiveSmallIntegerField(default=0)
    model_version = models.CharField(max_length=100, blank=True, default="")
    weight_config = models.JSONField(default=dict)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "scoring_fraudriskscore"
        indexes = [
            models.Index(fields=["tender", "computed_at"]),
        ]
        ordering = ["-computed_at"]

    def __str__(self):
        return f"Score {self.score} for Tender {self.tender_id} at {self.computed_at}"
