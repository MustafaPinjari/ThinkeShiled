from django.db import models
from django.utils import timezone


class SpecAnalysisResult(models.Model):
    tender = models.ForeignKey(
        "tenders.Tender", on_delete=models.CASCADE, related_name="spec_analyses"
    )
    # Embedding metadata
    embedding_model = models.CharField(
        max_length=200, default="paraphrase-multilingual-MiniLM-L12-v2"
    )
    embedding_dim = models.PositiveSmallIntegerField(default=384)
    spec_language = models.CharField(max_length=10, blank=True, default="")
    # Per-detector scores (null = detector did not run / insufficient data)
    tailoring_similarity = models.FloatField(null=True, blank=True)
    tailoring_matched_tender_id = models.IntegerField(null=True, blank=True)
    copy_paste_similarity = models.FloatField(null=True, blank=True)
    copy_paste_matched_tender_id = models.IntegerField(null=True, blank=True)
    vagueness_score = models.FloatField(null=True, blank=True)
    unusual_restriction_score = models.FloatField(null=True, blank=True)
    # Flags raised
    flags_raised = models.JSONField(default=list)
    # Processing metadata
    analyzed_at = models.DateTimeField(default=timezone.now)
    analysis_duration_ms = models.PositiveIntegerField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "nlp_specanalysisresult"
        indexes = [
            models.Index(fields=["tender", "analyzed_at"]),
        ]

    def __str__(self):
        return f"SpecAnalysisResult(tender_id={self.tender_id}, analyzed_at={self.analyzed_at})"


class SpecClauseHighlight(models.Model):
    tender = models.ForeignKey(
        "tenders.Tender", on_delete=models.CASCADE, related_name="clause_highlights"
    )
    red_flag = models.ForeignKey(
        "detection.RedFlag", on_delete=models.CASCADE, related_name="clause_highlights"
    )
    sentence_text = models.TextField()
    sentence_index = models.PositiveSmallIntegerField()  # 0-based position in spec_text
    relevance_score = models.FloatField()                # 0.0–1.0, higher = more relevant
    reason = models.CharField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "nlp_specclausehighlight"
        ordering = ["-relevance_score"]
        indexes = [
            models.Index(fields=["tender", "red_flag"]),
        ]

    def __str__(self):
        return f"SpecClauseHighlight(tender_id={self.tender_id}, score={self.relevance_score})"
