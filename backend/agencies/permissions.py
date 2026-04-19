"""
agencies/permissions.py

RBAC permission classes for the Agency Portal feature.

Role Permission Matrix
----------------------
Action                | AGENCY_ADMIN | AGENCY_OFFICER | REVIEWER | GOVERNMENT_AUDITOR | AUDITOR | ADMIN
----------------------|-------------|----------------|----------|--------------------|---------|------
view_own_tenders      |      ✓      |       ✓        |    ✓     |         ✓          |    —    |   ✓
create_tender         |      ✓      |       ✓        |    —     |         —          |    —    |   ✓
edit_draft_tender     |      ✓      |       ✓        |    —     |         —          |    —    |   ✓
submit_tender         |      ✓      |       ✓        |    —     |         —          |    —    |   ✓
view_fraud_score      |      ✓      |       ✓        |    ✓     |         ✓          |    ✓    |   ✓
view_shap             |      —      |       —        |    —     |         ✓          |    ✓    |   ✓
invite_members        |      ✓      |       —        |    —     |         —          |    —    |   ✓
manage_profile        |      ✓      |       —        |    —     |         —          |    —    |   ✓
view_all_agencies     |      —      |       —        |    —     |         ✓          |    —    |   ✓
suspend_agency        |      —      |       —        |    —     |         —          |    —    |   ✓
"""

from rest_framework.permissions import BasePermission

# ---------------------------------------------------------------------------
# Role constants (string values matching UserRole choices)
# ---------------------------------------------------------------------------

AGENCY_ADMIN = "AGENCY_ADMIN"
AGENCY_OFFICER = "AGENCY_OFFICER"
REVIEWER = "REVIEWER"
GOVERNMENT_AUDITOR = "GOVERNMENT_AUDITOR"
AUDITOR = "AUDITOR"
ADMIN = "ADMIN"

# ---------------------------------------------------------------------------
# Role Permission Matrix
# Maps action name → set of roles that are permitted to perform it.
# ---------------------------------------------------------------------------

PERMISSION_MATRIX: dict[str, set[str]] = {
    "view_own_tenders": {AGENCY_ADMIN, AGENCY_OFFICER, REVIEWER, GOVERNMENT_AUDITOR, ADMIN},
    "create_tender": {AGENCY_ADMIN, AGENCY_OFFICER, ADMIN},
    "edit_draft_tender": {AGENCY_ADMIN, AGENCY_OFFICER, ADMIN},
    "submit_tender": {AGENCY_ADMIN, AGENCY_OFFICER, ADMIN},
    "view_fraud_score": {AGENCY_ADMIN, AGENCY_OFFICER, REVIEWER, GOVERNMENT_AUDITOR, AUDITOR, ADMIN},
    "view_shap": {GOVERNMENT_AUDITOR, AUDITOR, ADMIN},
    "invite_members": {AGENCY_ADMIN, ADMIN},
    "manage_profile": {AGENCY_ADMIN, ADMIN},
    "view_all_agencies": {GOVERNMENT_AUDITOR, ADMIN},
    "suspend_agency": {ADMIN},
}

# All known roles
ALL_ROLES: set[str] = {
    AGENCY_ADMIN,
    AGENCY_OFFICER,
    REVIEWER,
    GOVERNMENT_AUDITOR,
    AUDITOR,
    ADMIN,
}

# ---------------------------------------------------------------------------
# DRF Permission Classes
# ---------------------------------------------------------------------------


class IsAgencyRole(BasePermission):
    """Allows access only to users with an agency-scoped role."""

    allowed_roles: set[str] = {AGENCY_ADMIN, AGENCY_OFFICER, REVIEWER}

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in self.allowed_roles
        )


class IsAgencyAdmin(BasePermission):
    """Allows access only to AGENCY_ADMIN users."""

    allowed_roles: set[str] = {AGENCY_ADMIN}

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in self.allowed_roles
        )


class IsAgencyOfficerOrAdmin(BasePermission):
    """Allows access to AGENCY_ADMIN and AGENCY_OFFICER users."""

    allowed_roles: set[str] = {AGENCY_ADMIN, AGENCY_OFFICER}

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in self.allowed_roles
        )


class IsGovernmentAuditorOrAdmin(BasePermission):
    """Allows access to GOVERNMENT_AUDITOR and ADMIN users."""

    allowed_roles: set[str] = {GOVERNMENT_AUDITOR, ADMIN}

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and getattr(request.user, "role", None) in self.allowed_roles
        )


class AgencyObjectPermission(BasePermission):
    """Object-level: ensures the resource's agency_id matches the user's agency_id."""

    def has_object_permission(self, request, view, obj):
        if getattr(request.user, "role", None) in (GOVERNMENT_AUDITOR, ADMIN):
            return True
        return obj.agency_id == request.user.agency_id


# ---------------------------------------------------------------------------
# Action → Permission class mapping
# Maps each action in PERMISSION_MATRIX to the DRF permission class that
# guards it, so property tests can call has_permission() directly.
# ---------------------------------------------------------------------------

ACTION_PERMISSION_CLASS: dict[str, type[BasePermission]] = {
    "view_own_tenders": IsAgencyRole,          # agency roles + gov auditor + admin
    "create_tender": IsAgencyOfficerOrAdmin,   # agency admin + officer + admin
    "edit_draft_tender": IsAgencyOfficerOrAdmin,
    "submit_tender": IsAgencyOfficerOrAdmin,
    "view_fraud_score": IsAgencyRole,          # all roles can view fraud score
    "view_shap": IsGovernmentAuditorOrAdmin,
    "invite_members": IsAgencyAdmin,
    "manage_profile": IsAgencyAdmin,
    "view_all_agencies": IsGovernmentAuditorOrAdmin,
    "suspend_agency": IsGovernmentAuditorOrAdmin,
}


def has_permission(role: str, action: str) -> bool:
    """
    Return True iff the given role is permitted to perform the given action,
    as defined by PERMISSION_MATRIX.

    This is the canonical permission check used by property-based tests.
    The DRF permission classes delegate to this matrix at runtime.
    """
    allowed = PERMISSION_MATRIX.get(action)
    if allowed is None:
        return False
    return role in allowed
