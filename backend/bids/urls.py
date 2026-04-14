from django.urls import path

from bids.views import BidRootView, BidBulkCreateView

urlpatterns = [
    # GET = list by tender_id, POST = create single bid
    path("", BidRootView.as_view(), name="bid-list-create"),
    path("bulk/", BidBulkCreateView.as_view(), name="bid-bulk-create"),
]
