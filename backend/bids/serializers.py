import bleach
from rest_framework import serializers

from bids.models import Bid, Bidder
from tenders.models import Tender


def _sanitize(value: str) -> str:
    return bleach.clean(value, tags=[], attributes={}, strip=True)


class BidSerializer(serializers.Serializer):
    """
    Validates and deserializes a single bid record.
    Fields: bid_id, tender_id, bidder_id, bidder_name, bid_amount, submission_timestamp.
    Optional: registered_address, director_names, is_winner.
    """

    bid_id = serializers.CharField(max_length=255, allow_blank=False)
    tender_id = serializers.CharField(max_length=255, allow_blank=False)
    bidder_id = serializers.CharField(max_length=255, allow_blank=False)
    bidder_name = serializers.CharField(max_length=500, allow_blank=False)
    bid_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    submission_timestamp = serializers.DateTimeField()

    # Optional bidder registry fields
    registered_address = serializers.CharField(
        max_length=1000, allow_blank=True, required=False, default=""
    )
    director_names = serializers.CharField(
        max_length=2000, allow_blank=True, required=False, default=""
    )
    is_winner = serializers.BooleanField(required=False, default=False)

    def validate_bid_id(self, value):
        return _sanitize(value)

    def validate_tender_id(self, value):
        return _sanitize(value)

    def validate_bidder_id(self, value):
        return _sanitize(value)

    def validate_bidder_name(self, value):
        return _sanitize(value)

    def validate_registered_address(self, value):
        return _sanitize(value)

    def validate_director_names(self, value):
        return _sanitize(value)

    def validate_bid_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("bid_amount must be a positive number.")
        return value

    def validate(self, attrs):
        # Verify the referenced tender exists
        tender_id = attrs.get("tender_id")
        try:
            attrs["_tender"] = Tender.objects.get(tender_id=tender_id)
        except Tender.DoesNotExist:
            raise serializers.ValidationError(
                {"tender_id": [f"Tender with tender_id '{tender_id}' does not exist."]}
            )
        return attrs

    def create_bid(self) -> tuple["Bid", "Bidder", bool]:
        """
        Upsert the Bidder record and create the Bid.
        Returns (bid, bidder, bidder_created).
        Raises IntegrityError if bid_id already exists.
        """
        data = self.validated_data
        tender = data["_tender"]

        bidder, bidder_created = Bidder.objects.update_or_create(
            bidder_id=data["bidder_id"],
            defaults={
                "bidder_name": data["bidder_name"],
                "registered_address": data.get("registered_address", ""),
                "director_names": data.get("director_names", ""),
            },
        )

        bid = Bid.objects.create(
            bid_id=data["bid_id"],
            tender=tender,
            bidder=bidder,
            bid_amount=data["bid_amount"],
            submission_timestamp=data["submission_timestamp"],
            is_winner=data.get("is_winner", False),
        )

        return bid, bidder, bidder_created


class BidReadSerializer(serializers.ModelSerializer):
    """Read-only serializer for Bid — includes bidder fields for list views."""

    bidder_id = serializers.CharField(source="bidder.bidder_id", read_only=True)
    bidder_name = serializers.CharField(source="bidder.bidder_name", read_only=True)
    tender_id = serializers.CharField(source="tender.tender_id", read_only=True)

    class Meta:
        model = Bid
        fields = [
            "id",
            "bid_id",
            "tender_id",
            "bidder_id",
            "bidder_name",
            "bid_amount",
            "submission_timestamp",
            "is_winner",
            "created_at",
        ]
