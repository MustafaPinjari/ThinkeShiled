from django.db import models
from django.utils import timezone


class Bidder(models.Model):
    bidder_id = models.CharField(max_length=255, unique=True)
    bidder_name = models.CharField(max_length=500)
    registered_address = models.TextField(blank=True, default="")
    director_names = models.TextField(blank=True, default="")  # comma-separated list
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "bids_bidder"
        indexes = [
            models.Index(fields=["bidder_name"]),
        ]

    def __str__(self):
        return f"{self.bidder_id}: {self.bidder_name}"

    def get_director_list(self):
        """Return director names as a list."""
        if not self.director_names:
            return []
        return [d.strip() for d in self.director_names.split(",") if d.strip()]


class Bid(models.Model):
    bid_id = models.CharField(max_length=255, unique=True)
    tender = models.ForeignKey(
        "tenders.Tender", on_delete=models.CASCADE, related_name="bids"
    )
    bidder = models.ForeignKey(
        Bidder, on_delete=models.CASCADE, related_name="bids"
    )
    bid_amount = models.DecimalField(max_digits=20, decimal_places=2)
    submission_timestamp = models.DateTimeField()
    is_winner = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "bids_bid"
        indexes = [
            models.Index(fields=["tender"]),
            models.Index(fields=["bidder"]),
            models.Index(fields=["submission_timestamp"]),
        ]

    def __str__(self):
        return f"Bid {self.bid_id} on Tender {self.tender_id}"
