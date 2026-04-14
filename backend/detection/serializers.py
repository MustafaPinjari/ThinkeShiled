from rest_framework import serializers
from detection.models import RuleDefinition


class RuleDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RuleDefinition
        fields = [
            "id",
            "rule_code",
            "description",
            "severity",
            "is_active",
            "parameters",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
