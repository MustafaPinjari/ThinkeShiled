"""
agencies/serializers.py

Extends TokenObtainPairSerializer to inject `agency_id` and `role` into the
JWT payload, and to block authentication for users whose agency is SUSPENDED.

Satisfies Requirement 9.2.
"""

from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import AgencyStatus


class AgencyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Custom JWT serializer that:
    1. Injects `role` and `agency_id` claims into the JWT payload so that
       downstream permission checks are stateless (Requirement 9.2).
    2. Blocks login for users whose agency is SUSPENDED, returning HTTP 403
       with a human-readable message (Requirement 9.7).
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["role"] = user.role
        # Use the UUID agency_id (agency.agency_id), not the integer FK (agency_id)
        if user.agency_id:
            try:
                token["agency_id"] = str(user.agency.agency_id)
            except Exception:
                token["agency_id"] = str(user.agency_id)
        else:
            token["agency_id"] = None
        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # Block suspended agency members from obtaining a token.
        user = self.user
        if user.agency and user.agency.status == AgencyStatus.SUSPENDED:
            raise AuthenticationFailed(
                "Your agency account is suspended. Contact support@tendershield.in."
            )

        return data
