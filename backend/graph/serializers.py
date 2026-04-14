from rest_framework import serializers
from graph.models import CollusionRing


class CollusionRingSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollusionRing
        fields = [
            "ring_id",
            "member_bidder_ids",
            "member_count",
            "detected_at",
            "is_active",
        ]
