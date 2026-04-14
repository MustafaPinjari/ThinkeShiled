from rest_framework import serializers

from companies.models import CompanyProfile


class CompanyProfileSerializer(serializers.ModelSerializer):
    bidder_id = serializers.CharField(source="bidder.bidder_id", read_only=True)
    bidder_name = serializers.CharField(source="bidder.bidder_name", read_only=True)
    collusion_ring_id = serializers.CharField(
        source="collusion_ring.ring_id", read_only=True, allow_null=True
    )

    class Meta:
        model = CompanyProfile
        fields = [
            "id",
            "bidder_id",
            "bidder_name",
            "total_bids",
            "total_wins",
            "win_rate",
            "avg_bid_deviation",
            "active_red_flag_count",
            "highest_fraud_risk_score",
            "risk_status",
            "collusion_ring_id",
            "updated_at",
        ]
