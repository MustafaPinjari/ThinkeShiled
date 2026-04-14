from rest_framework.permissions import BasePermission
from authentication.models import UserRole


class IsAdminRole(BasePermission):
    """Allow access only to users with the ADMIN role."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == UserRole.ADMIN
        )


class IsAuditorOrAdmin(BasePermission):
    """Allow access to users with AUDITOR or ADMIN role."""

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in (UserRole.AUDITOR, UserRole.ADMIN)
        )
