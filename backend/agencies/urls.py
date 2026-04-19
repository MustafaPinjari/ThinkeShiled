"""
agencies/urls.py

URL routing for all Agency Portal RBAC API endpoints.
Registered under api/v1/agencies/ in config/urls.py (task 9.2).
"""

from django.urls import path

from agencies.views import (
    AgencyMemberDeactivateView,
    AgencyMemberListView,
    AgencyProfileView,
    AgencyRegisterView,
    AgencyTenderDetailView,
    AgencyTenderListView,
    AgencyTenderSubmitView,
    CrossAgencyTenderListView,
    EmailVerificationView,
    InvitationAcceptView,
    InvitationCreateView,
    TenderClearView,
)

urlpatterns = [
    # --- Public: registration & email verification ---
    path("register/", AgencyRegisterView.as_view(), name="agency-register"),
    path("verify-email/", EmailVerificationView.as_view(), name="agency-verify-email"),

    # --- Invitations ---
    path("me/invitations/", InvitationCreateView.as_view(), name="agency-invitation-create"),
    path("me/invitations/accept/", InvitationAcceptView.as_view(), name="agency-invitation-accept"),

    # --- Agency profile ---
    path("me/", AgencyProfileView.as_view(), name="agency-profile"),

    # --- Member management ---
    path("me/members/", AgencyMemberListView.as_view(), name="agency-member-list"),
    path(
        "me/members/<int:pk>/deactivate/",
        AgencyMemberDeactivateView.as_view(),
        name="agency-member-deactivate",
    ),

    # --- Agency-scoped tender submissions ---
    path("me/tenders/", AgencyTenderListView.as_view(), name="agency-tender-list"),
    path("me/tenders/<int:pk>/", AgencyTenderDetailView.as_view(), name="agency-tender-detail"),
    path(
        "me/tenders/<int:pk>/submit/",
        AgencyTenderSubmitView.as_view(),
        name="agency-tender-submit",
    ),

    # --- Cross-agency (Government Auditor / Admin) ---
    path("tenders/", CrossAgencyTenderListView.as_view(), name="cross-agency-tender-list"),
    path(
        "tenders/<int:pk>/clear/",
        TenderClearView.as_view(),
        name="agency-tender-clear",
    ),
]
