from collections import defaultdict

from rest_framework import serializers

from nlp.models import SpecAnalysisResult, SpecClauseHighlight


class SpecClauseHighlightSerializer(serializers.ModelSerializer):
    flag_type = serializers.CharField(source="red_flag.flag_type", read_only=True)

    class Meta:
        model = SpecClauseHighlight
        fields = [
            "id",
            "flag_type",
            "sentence_text",
            "sentence_index",
            "relevance_score",
            "reason",
            "created_at",
        ]


class SpecAnalysisResultSerializer(serializers.ModelSerializer):
    highlights_by_flag_type = serializers.SerializerMethodField()

    class Meta:
        model = SpecAnalysisResult
        fields = [
            "id",
            "tender_id",
            "embedding_model",
            "embedding_dim",
            "spec_language",
            "tailoring_similarity",
            "tailoring_matched_tender_id",
            "copy_paste_similarity",
            "copy_paste_matched_tender_id",
            "vagueness_score",
            "unusual_restriction_score",
            "flags_raised",
            "analyzed_at",
            "analysis_duration_ms",
            "error",
            "highlights_by_flag_type",
        ]

    def get_highlights_by_flag_type(self, obj):
        highlights = (
            SpecClauseHighlight.objects.filter(tender=obj.tender)
            .select_related("red_flag")
            .order_by("-relevance_score")
        )
        grouped = defaultdict(list)
        for highlight in highlights:
            flag_type = highlight.red_flag.flag_type
            grouped[flag_type].append(SpecClauseHighlightSerializer(highlight).data)
        return dict(grouped)
