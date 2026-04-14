"""DRF serializers for the Alerts app."""

from rest_framework import serializers

from alerts.models import Alert, AlertSettings


class AlertSerializer(serializers.ModelSerializer):
    tender_id = serializers.IntegerField(source="tender.id", read_only=True)
    tender_external_id = serializers.CharField(source="tender.tender_id", read_only=True)

    class Meta:
        model = Alert
        fields = [
            "id",
            "tender_id",
            "tender_external_id",
            "title",
            "detail_link",
            "alert_type",
            "fraud_risk_score",
            "top_red_flags",
            "delivery_status",
            "retry_count",
            "is_read",
            "created_at",
            "delivered_at",
        ]
        read_only_fields = fields


class AlertSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertSettings
        fields = ["id", "threshold", "category", "email_enabled"]

    def validate_threshold(self, value):
        if not (0 <= value <= 100):
            raise serializers.ValidationError("Threshold must be between 0 and 100.")
        return value
