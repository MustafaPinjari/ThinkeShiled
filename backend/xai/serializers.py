"""
Serializers for XAI explanation responses.
"""

from rest_framework import serializers


class TopFactorSerializer(serializers.Serializer):
    feature = serializers.CharField()
    shap_value = serializers.FloatField()
    feature_value = serializers.FloatField()
    explanation = serializers.CharField()


class RedFlagExplanationSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    flag_type = serializers.CharField()
    severity = serializers.CharField()
    rule_version = serializers.CharField()
    trigger_data = serializers.DictField()
    raised_at = serializers.CharField(allow_null=True)
    rule_text = serializers.CharField(allow_blank=True)


class ExplanationSerializer(serializers.Serializer):
    tender_id = serializers.IntegerField()
    model_version = serializers.CharField(allow_blank=True)
    rule_engine_version = serializers.CharField(allow_blank=True)
    shap_values = serializers.DictField(child=serializers.FloatField(), allow_empty=True)
    top_factors = TopFactorSerializer(many=True)
    red_flags = RedFlagExplanationSerializer(many=True)
    shap_failed = serializers.BooleanField()
    computed_at = serializers.CharField(allow_null=True)
