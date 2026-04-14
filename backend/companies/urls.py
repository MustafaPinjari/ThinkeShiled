from django.urls import path

from companies.views import (
    CompanyListView,
    CompanyDetailView,
    CompanyTendersView,
    CompanyRedFlagsView,
)

urlpatterns = [
    path("", CompanyListView.as_view(), name="company-list"),
    path("<int:pk>/", CompanyDetailView.as_view(), name="company-detail"),
    path("<int:pk>/tenders/", CompanyTendersView.as_view(), name="company-tenders"),
    path("<int:pk>/red-flags/", CompanyRedFlagsView.as_view(), name="company-red-flags"),
]
