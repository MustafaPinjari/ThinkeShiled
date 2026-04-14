from django.urls import path

from alerts.views import (
    AlertDetailView,
    AlertListView,
    AlertMarkReadView,
    AlertSettingsView,
    AlertUnreadView,
)

urlpatterns = [
    path("", AlertListView.as_view(), name="alert-list"),
    path("unread/", AlertUnreadView.as_view(), name="alert-unread"),
    path("settings/", AlertSettingsView.as_view(), name="alert-settings"),
    path("<int:pk>/", AlertDetailView.as_view(), name="alert-detail"),
    path("<int:pk>/read/", AlertMarkReadView.as_view(), name="alert-mark-read"),
]
