from django.urls import path

from nlp.views import TenderSpecAnalysisView
from tenders.views import (
    TenderRootView,
    TenderCSVUploadView,
    TenderDetailView,
    TenderExplanationView,
    TenderMarkFraudCorpusView,
    TenderRedFlagsView,
    TenderRescoreView,
    TenderScoreHistoryView,
    TenderScoreView,
    TenderSpecUpdateView,
    TenderStatsView,
    TenderStatusChangeView,
)

urlpatterns = [
    # GET = list (AUDITOR/ADMIN), POST = create single (ADMIN)
    path("", TenderRootView.as_view(), name="tender-list-create"),
    path("upload/", TenderCSVUploadView.as_view(), name="tender-csv-upload"),
    # Dashboard summary stats — must be before <int:pk>/ to avoid conflict
    path("stats/", TenderStatsView.as_view(), name="tender-stats"),
    # Detail and sub-resources
    path("<int:pk>/", TenderDetailView.as_view(), name="tender-detail"),
    path("<int:pk>/score/", TenderScoreView.as_view(), name="tender-score"),
    path("<int:pk>/explanation/", TenderExplanationView.as_view(), name="tender-explanation"),
    path("<int:pk>/red-flags/", TenderRedFlagsView.as_view(), name="tender-red-flags"),
    path("<int:pk>/score-history/", TenderScoreHistoryView.as_view(), name="tender-score-history"),
    path("<int:pk>/rescore/", TenderRescoreView.as_view(), name="tender-rescore"),
    path("<int:pk>/status/", TenderStatusChangeView.as_view(), name="tender-status-change"),
    path("<int:pk>/spec/", TenderSpecUpdateView.as_view(), name="tender-spec-update"),
    path("<int:pk>/spec-analysis/", TenderSpecAnalysisView.as_view(), name="tender-spec-analysis"),
    path("<int:pk>/mark-fraud-corpus/", TenderMarkFraudCorpusView.as_view(), name="tender-mark-fraud-corpus"),
]
