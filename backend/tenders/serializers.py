import bleach
from rest_framework import serializers

from tenders.models import Tender, TenderStatus

# Fields that should be sanitized with bleach
_STRING_FIELDS = ["tender_id", "title", "category", "currency", "buyer_id", "buyer_name"]


def _sanitize(value: str) -> str:
    """Strip all HTML tags and attributes from a string."""
    return bleach.clean(value, tags=[], attributes={}, strip=True)


class TenderSerializer(serializers.ModelSerializer):
    """Serializer for Tender — validates OCDS-inspired fields and sanitizes strings."""

    # Mandatory fields (non-blank enforced via allow_blank=False)
    tender_id = serializers.CharField(max_length=255, allow_blank=False)
    title = serializers.CharField(max_length=500, allow_blank=False)
    category = serializers.CharField(max_length=255, allow_blank=False)
    estimated_value = serializers.DecimalField(max_digits=20, decimal_places=2)
    currency = serializers.CharField(max_length=10, allow_blank=False)
    submission_deadline = serializers.DateTimeField()
    buyer_id = serializers.CharField(max_length=255, allow_blank=False)
    buyer_name = serializers.CharField(max_length=500, allow_blank=False)

    # Optional fields
    status = serializers.ChoiceField(
        choices=TenderStatus.choices,
        default=TenderStatus.ACTIVE,
        required=False,
    )
    publication_date = serializers.DateTimeField(required=False, allow_null=True)

    class Meta:
        model = Tender
        fields = [
            "id",
            "tender_id",
            "title",
            "category",
            "estimated_value",
            "currency",
            "submission_deadline",
            "buyer_id",
            "buyer_name",
            "status",
            "publication_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        # Sanitize all string fields
        for field in _STRING_FIELDS:
            if field in attrs and attrs[field]:
                attrs[field] = _sanitize(attrs[field])
        return attrs

    def validate_tender_id(self, value):
        value = _sanitize(value)
        if not value:
            raise serializers.ValidationError("tender_id may not be blank.")
        return value

    def validate_title(self, value):
        return _sanitize(value)

    def validate_category(self, value):
        return _sanitize(value)

    def validate_currency(self, value):
        return _sanitize(value)

    def validate_buyer_id(self, value):
        return _sanitize(value)

    def validate_buyer_name(self, value):
        return _sanitize(value)


class TenderListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view — includes computed score fields."""

    latest_score = serializers.IntegerField(read_only=True, allow_null=True)
    active_red_flag_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Tender
        fields = [
            "id",
            "tender_id",
            "title",
            "category",
            "estimated_value",
            "currency",
            "submission_deadline",
            "buyer_id",
            "buyer_name",
            "status",
            "created_at",
            "latest_score",
            "active_red_flag_count",
        ]
