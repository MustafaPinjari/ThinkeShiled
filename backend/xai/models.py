from django.db import models
from django.utils import timezone


class MLModelType(models.TextChoices):
    ISOLATION_FOREST = "ISOLATION_FOREST", "Isolation Forest"
    RANDOM_FOREST = "RANDOM_FOREST", "Random Forest"


class MLModelVersion(models.Model):
    model_type = models.CharField(max_length=50, choices=MLModelType.choices)
    version = models.CharField(max_length=100)
    trained_at = models.DateTimeField(default=timezone.now)
    feature_importances = models.JSONField(default=dict)
    model_artifact_path = models.CharField(max_length=500)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "xai_mlmodelversion"
        indexes = [
            models.Index(fields=["model_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.model_type} v{self.version} ({'active' if self.is_active else 'inactive'})"


class SHAPExplanation(models.Model):
    tender = models.ForeignKey(
        "tenders.Tender", on_delete=models.CASCADE, related_name="shap_explanations"
    )
    model_version = models.CharField(max_length=100)
    rule_engine_version = models.CharField(max_length=100)
    shap_values = models.JSONField(default=dict)
    top_factors = models.JSONField(default=list)
    shap_failed = models.BooleanField(default=False)
    computed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "xai_shapexplanation"
        indexes = [
            models.Index(fields=["tender", "computed_at"]),
        ]
        ordering = ["-computed_at"]

    def __str__(self):
        status = "failed" if self.shap_failed else "ok"
        return f"SHAP for Tender {self.tender_id} v{self.model_version} ({status})"
