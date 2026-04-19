"""
agencies/jwt_auth.py

Extends AuditingJWTAuthentication to block authentication for users whose
agency has been suspended, satisfying Requirements 2.5 and 9.7.
"""

from rest_framework_simplejwt.exceptions import AuthenticationFailed

from authentication.jwt_auth import AuditingJWTAuthentication

from .models import AgencyStatus


class AgencyAwareJWTAuthentication(AuditingJWTAuthentication):
    """
    JWT authentication backend that additionally checks agency suspension.

    After the parent class resolves the user from the validated token, this
    subclass checks whether the user's agency is SUSPENDED. If so, it raises
    AuthenticationFailed before returning the user, ensuring that suspended
    agency members cannot authenticate regardless of their own is_active state.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if user.agency and user.agency.status == AgencyStatus.SUSPENDED:
            raise AuthenticationFailed("Agency account is suspended.")
        return user
