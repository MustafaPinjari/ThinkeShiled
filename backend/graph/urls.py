from django.urls import path
from graph.views import GraphDataView, CollusionRingListView, CollusionRingDetailView

urlpatterns = [
    path("", GraphDataView.as_view(), name="graph-data"),
    path("rings/", CollusionRingListView.as_view(), name="collusion-ring-list"),
    path("rings/<str:ring_id>/", CollusionRingDetailView.as_view(), name="collusion-ring-detail"),
]
