"""
agencies/views.py — stub views for URL routing.
Full implementations are in individual task files.
"""
from rest_framework.views import APIView
from rest_framework.response import Response


class _StubView(APIView):
    def get(self, request, *args, **kwargs):
        return Response({"detail": "Not implemented"}, status=501)

    def post(self, request, *args, **kwargs):
        return Response({"detail": "Not implemented"}, status=501)

    def patch(self, request, *args, **kwargs):
        return Response({"detail": "Not implemented"}, status=501)


AgencyRegisterView = _StubView
EmailVerificationView = _StubView
InvitationCreateView = _StubView
InvitationAcceptView = _StubView
AgencyProfileView = _StubView
AgencyMemberListView = _StubView
AgencyMemberDeactivateView = _StubView
AgencyTenderListView = _StubView
AgencyTenderDetailView = _StubView
AgencyTenderSubmitView = _StubView
CrossAgencyTenderListView = _StubView
TenderClearView = _StubView
