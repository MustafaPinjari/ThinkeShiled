"""
agencies/views.py

Agency Portal RBAC API views.

Tasks implemented here:
  3.1 — AgencyRegisterView  (POST /api/v1/agencies/register/)
  3.2 — EmailVerificationView (GET /api/v1/agencies/verify-email/)
  3.4 — AgencyLoginView  (POST /api/v1/agencies/login/)
  4.1 — InvitationCreateView (POST /api/v1/agencies/me/invitations/)
  4.2 — InvitationAcceptView GET (GET /api/v1/agencies/me/invitations/accept/)
  4.3 — InvitationAcceptView POST (POST /api/v1/agencies/me/invitations/accept/)
  4.5 — AgencyMemberListView (GET /api/v1/agencies/me/members/)
  4.6 — AgencyMemberDeactivateView (PATCH /api/v1/agencies/me/members/<id>/deactivate/)
  6.1 — AgencyTenderListView GET (GET /api/v1/agencies/me/tenders/)
  6.2 — AgencyTenderListView POST (POST /api/v1/agencies/me/tenders/)
  6.3 — AgencyTenderDetailView GET (GET /api/v1/agencies/me/tenders/<id>/)
  6.4 — AgencyTenderDetailView PATCH (PATCH /api/v1/agencies/me/tenders/<id>/)
  6.5 — AgencyTenderDetailView DELETE (DELETE /api/v1/agencies/me/tenders/<id>/)
  6.6 — AgencyTenderSubmitView (POST /api/v1/agencies/me/tenders/<id>/submit/)
  6.7 — CrossAgencyTenderListView (GET /api/v1/agencies/tenders/)
  6.8 — TenderClearView (PATCH /api/v1/agencies/tenders/<id>/clear/)
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from audit.models import AuditLog, EventType
from authentication.models import User, UserRole

from .models import (
    Agency,
    AgencyStatus,
    EmailVerificationToken,
    Invitation,
    SubmissionStatus,
    TenderSubmission,
)
from .permissions import (
    IsAgencyAdmin,
    IsAgencyOfficerOrAdmin,
    IsAgencyRole,
    IsGovernmentAuditorOrAdmin,
    AGENCY_OFFICER,
)
from .sanitize import bleach_clean
from .validators import validate_gstin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _sha256_hex(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Task 3.1 — Agency Registration
# ---------------------------------------------------------------------------

class AgencyRegisterView(APIView):
    """
    POST /api/v1/agencies/register/

    Public endpoint. Creates an Agency (PENDING_APPROVAL) and an Agency_Admin
    User (is_active=False), issues an EmailVerificationToken, and enqueues the
    send_verification_email Celery task.

    Requirements: 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.7
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        data = request.data

        # --- Required field validation ---
        required_fields = [
            "legal_name",
            "gstin",
            "ministry",
            "contact_name",
            "contact_email",
            "password",
        ]
        missing = [f for f in required_fields if not data.get(f, "").strip()]
        if missing:
            return Response(
                {"detail": "Missing required fields.", "missing_fields": missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        legal_name = data["legal_name"].strip()
        gstin = data["gstin"].strip().upper()
        ministry = data["ministry"].strip()
        contact_name = data["contact_name"].strip()
        contact_email = data["contact_email"].strip().lower()
        password = data["password"]

        # --- GSTIN format validation (Requirement 2.7) ---
        try:
            validate_gstin(gstin)
        except ValidationError as exc:
            return Response(
                {"detail": str(exc.message)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- GSTIN uniqueness (Requirement 1.5) ---
        if Agency.objects.filter(gstin=gstin).exists():
            return Response(
                {"detail": "An agency with this GSTIN is already registered."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Email uniqueness (Requirement 1.6) ---
        if User.objects.filter(email=contact_email).exists():
            return Response(
                {"detail": "This email address is already associated with an account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Create Agency ---
        agency = Agency.objects.create(
            legal_name=legal_name,
            gstin=gstin,
            ministry=ministry,
            contact_name=contact_name,
            contact_email=contact_email,
            status=AgencyStatus.PENDING_APPROVAL,
        )

        # --- Create Agency_Admin User (is_active=False until email verified) ---
        # Username derived from email local part + agency pk to ensure uniqueness
        base_username = contact_email.split("@")[0]
        username = f"{base_username}_{agency.pk}"
        user = User.objects.create_user(
            username=username,
            email=contact_email,
            password=password,
            role=UserRole.AGENCY_ADMIN,
        )
        user.is_active = False
        user.agency = agency
        user.save(update_fields=["is_active", "agency_id"])

        # --- Create EmailVerificationToken (24-hour expiry, SHA-256 stored) ---
        raw_token = os.urandom(32)
        token_hash = _sha256_hex(raw_token)
        token_hex = raw_token.hex()  # sent in the email link

        EmailVerificationToken.objects.create(
            user=user,
            token_hash=token_hash,
            expires_at=timezone.now() + timedelta(hours=24),
        )

        # --- Enqueue verification email ---
        try:
            from agencies.tasks import send_verification_email  # noqa: PLC0415
            send_verification_email.delay(user.pk, token_hex, agency.legal_name)
        except Exception as exc:
            logger.warning(
                "Failed to enqueue send_verification_email for user %d: %s", user.pk, exc
            )

        # --- Write AuditLog ---
        AuditLog.objects.create(
            event_type=EventType.AGENCY_REGISTERED,
            user=user,
            affected_entity_type="Agency",
            affected_entity_id=str(agency.agency_id),
            data_snapshot={
                "legal_name": legal_name,
                "gstin": gstin,
                "ministry": ministry,
                "contact_email": contact_email,
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(
            {"message": "Registration successful. Please check your email to verify your account."},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Task 3.2 — Email Verification
# ---------------------------------------------------------------------------

class EmailVerificationView(APIView):
    """
    GET /api/v1/agencies/verify-email/?token=<hex>

    Public endpoint. Verifies the email address by looking up the
    EmailVerificationToken by its SHA-256 hash.

    Requirements: 1.9, 2.3
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        token_hex = request.query_params.get("token", "").strip()
        if not token_hex:
            return Response(
                {"detail": "Token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Hash the incoming token to look up the stored record
        try:
            raw_bytes = bytes.fromhex(token_hex)
        except ValueError:
            return Response(
                {"detail": "Invalid token format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token_hash = _sha256_hex(raw_bytes)

        try:
            verification = EmailVerificationToken.objects.select_related(
                "user", "user__agency"
            ).get(token_hash=token_hash)
        except EmailVerificationToken.DoesNotExist:
            return Response(
                {"detail": "Invalid or expired verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check expiry
        if verification.expires_at < timezone.now():
            return Response(
                {"detail": "Invalid or expired verification token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = verification.user
        agency = user.agency

        # Activate user and agency
        user.is_active = True
        user.email_verified = True
        user.save(update_fields=["is_active", "email_verified"])

        if agency:
            agency.status = AgencyStatus.ACTIVE
            agency.approved_at = timezone.now()
            agency.save(update_fields=["status", "approved_at"])

        # Write AuditLog
        AuditLog.objects.create(
            event_type=EventType.AGENCY_STATUS_CHANGED,
            user=user,
            affected_entity_type="Agency",
            affected_entity_id=str(agency.agency_id) if agency else "",
            data_snapshot={
                "previous_status": AgencyStatus.PENDING_APPROVAL,
                "new_status": AgencyStatus.ACTIVE,
                "triggered_by": "email_verification",
            },
        )

        # Clean up the token (optional but good hygiene)
        verification.delete()

        return Response(
            {"message": "Email verified successfully. You can now log in."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Task 3.4 — Agency Login with rate-limiting and account lockout
# ---------------------------------------------------------------------------

LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION_MINUTES = 15


class AgencyLoginView(APIView):
    """
    POST /api/v1/agencies/login/

    Agency-specific login view that:
    - Uses AgencyTokenObtainPairSerializer to inject agency_id and role into JWT
    - Checks account lockout before authenticating
    - On success: resets failed_login_attempts and locked_until
    - On failure: increments failed_login_attempts; locks account after 5 failures
    - Writes USER_LOCKED AuditLog entry on lockout (Requirement 9.6)
    - Writes USER_LOGIN / USER_LOGIN_FAILED AuditLog entries (Requirement 9.3)

    Requirements: 9.5, 9.6
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email", "").strip().lower()
        password = request.data.get("password", "")
        ip = _get_ip(request)

        if not email or not password:
            return Response(
                {"detail": "Email and password are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Look up user by email
        try:
            user_obj = User.objects.select_related("agency").get(email=email)
        except User.DoesNotExist:
            # Don't reveal whether the email exists
            return Response(
                {"detail": "Invalid credentials.", "failed_attempts": 0},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Check account lockout (Requirement 9.5)
        if user_obj.is_locked():
            return Response(
                {
                    "detail": (
                        f"Account locked due to too many failed login attempts. "
                        f"Try again after {user_obj.locked_until.isoformat()}."
                    ),
                    "locked_until": user_obj.locked_until.isoformat(),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Check suspended agency (Requirement 9.7)
        if user_obj.agency and user_obj.agency.status == AgencyStatus.SUSPENDED:
            return Response(
                {"detail": "Your agency account is suspended. Contact support@tendershield.in."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Authenticate using username (Django's authenticate uses USERNAME_FIELD)
        user = authenticate(request, username=user_obj.username, password=password)

        if user is not None:
            # Successful login — reset counters
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=["failed_login_attempts", "locked_until"])

            # Issue JWT tokens using AgencyTokenObtainPairSerializer
            from .serializers import AgencyTokenObtainPairSerializer  # noqa: PLC0415
            refresh = AgencyTokenObtainPairSerializer.get_token(user)
            access = refresh.access_token

            AuditLog.objects.create(
                event_type=EventType.USER_LOGIN,
                user=user,
                affected_entity_type="User",
                affected_entity_id=str(user.pk),
                data_snapshot={
                    "email": user.email,
                    "agency_id": str(user.agency_id) if user.agency_id else None,
                    "role": user.role,
                },
                ip_address=ip or None,
            )

            return Response(
                {
                    "access": str(access),
                    "refresh": str(refresh),
                    "expires_in": int(access.lifetime.total_seconds()),
                    "role": user.role,
                    "agency_id": str(user.agency_id) if user.agency_id else None,
                },
                status=status.HTTP_200_OK,
            )

        # Failed authentication — increment counter
        user_obj.failed_login_attempts += 1
        now = timezone.now()

        if user_obj.failed_login_attempts >= LOCKOUT_THRESHOLD:
            user_obj.locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            user_obj.save(update_fields=["failed_login_attempts", "locked_until"])

            # Write USER_LOCKED AuditLog entry (Requirement 9.6)
            AuditLog.objects.create(
                event_type=EventType.USER_LOCKED,
                user=user_obj,
                affected_entity_type="User",
                affected_entity_id=str(user_obj.pk),
                data_snapshot={
                    "email": user_obj.email,
                    "locked_until": user_obj.locked_until.isoformat(),
                    "failed_attempts": user_obj.failed_login_attempts,
                },
                ip_address=ip or None,
            )
        else:
            user_obj.save(update_fields=["failed_login_attempts"])

        # Write USER_LOGIN_FAILED AuditLog entry
        AuditLog.objects.create(
            event_type=EventType.USER_LOGIN_FAILED,
            user=user_obj,
            affected_entity_type="User",
            affected_entity_id=str(user_obj.pk),
            data_snapshot={
                "email": user_obj.email,
                "failed_attempts": user_obj.failed_login_attempts,
            },
            ip_address=ip or None,
        )

        return Response(
            {
                "detail": "Invalid credentials.",
                "failed_attempts": user_obj.failed_login_attempts,
            },
            status=status.HTTP_401_UNAUTHORIZED,
        )


# ---------------------------------------------------------------------------
# Stub views — implemented in later tasks
# ---------------------------------------------------------------------------

class _StubView(APIView):
    def get(self, request, *args, **kwargs):
        return Response({"detail": "Not implemented"}, status=501)

    def post(self, request, *args, **kwargs):
        return Response({"detail": "Not implemented"}, status=501)

    def patch(self, request, *args, **kwargs):
        return Response({"detail": "Not implemented"}, status=501)


# ---------------------------------------------------------------------------
# Task 4.1 — Invitation Create
# POST /api/v1/agencies/me/invitations/
# Requirements: 4.1, 4.2, 4.6, 4.9
# ---------------------------------------------------------------------------

_INVITABLE_ROLES = {UserRole.AGENCY_OFFICER, UserRole.REVIEWER}


class InvitationCreateView(APIView):
    """
    POST /api/v1/agencies/me/invitations/

    AGENCY_ADMIN only. Creates an Invitation record, enqueues the
    send_invitation_email Celery task, and writes an INVITATION_CREATED
    AuditLog entry.

    Requirements: 4.1, 4.2, 4.6, 4.9
    """

    permission_classes = [IsAgencyAdmin]

    def post(self, request):
        data = request.data
        email = (data.get("email") or "").strip().lower()
        role = (data.get("role") or "").strip().upper()

        if not email:
            return Response(
                {"detail": "Email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not role:
            return Response(
                {"detail": "Role is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Requirement 4.6: only AGENCY_OFFICER or REVIEWER may be invited
        if role not in _INVITABLE_ROLES:
            return Response(
                {"detail": "You can only invite users with role AGENCY_OFFICER or REVIEWER."},
                status=status.HTTP_403_FORBIDDEN,
            )

        agency = request.user.agency
        if agency is None:
            return Response(
                {"detail": "Your account is not associated with an agency."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Generate 32-byte cryptographically random token
        raw_token = os.urandom(32)
        token_hex = raw_token.hex()
        token_hash = _sha256_hex(raw_token)

        expires_at = timezone.now() + timedelta(hours=72)

        invitation = Invitation.objects.create(
            token_hash=token_hash,
            email=email,
            role=role,
            agency=agency,
            invited_by=request.user,
            expires_at=expires_at,
        )

        # Enqueue invitation email
        try:
            from agencies.tasks import send_invitation_email  # noqa: PLC0415
            send_invitation_email.delay(invitation.pk, token_hex)
        except Exception as exc:
            logger.warning(
                "Failed to enqueue send_invitation_email for invitation %d: %s",
                invitation.pk,
                exc,
            )

        # Write AuditLog
        AuditLog.objects.create(
            event_type=EventType.INVITATION_CREATED,
            user=request.user,
            affected_entity_type="Invitation",
            affected_entity_id=str(invitation.pk),
            data_snapshot={
                "email": email,
                "role": role,
                "agency_id": str(agency.agency_id),
                "expires_at": expires_at.isoformat(),
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(
            {
                "message": "Invitation sent.",
                "expires_at": expires_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Task 4.2 & 4.3 — Invitation Accept (GET + POST)
# GET/POST /api/v1/agencies/me/invitations/accept/
# Requirements: 4.3, 4.4, 4.5, 4.9
# ---------------------------------------------------------------------------

_INVITATION_EXPIRED_MSG = "This invitation has expired or has already been used."


def _lookup_invitation(token_param: str):
    """
    Look up an Invitation by the raw token hex string.
    Returns (invitation, error_response) — one of them will be None.
    """
    if not token_param:
        return None, Response(
            {"detail": "Token is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        raw_bytes = bytes.fromhex(token_param)
    except ValueError:
        return None, Response(
            {"detail": "Invalid token format."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    token_hash = _sha256_hex(raw_bytes)

    try:
        invitation = Invitation.objects.select_related("agency").get(token_hash=token_hash)
    except Invitation.DoesNotExist:
        return None, Response(
            {"detail": _INVITATION_EXPIRED_MSG},
            status=status.HTTP_410_GONE,
        )

    if not invitation.is_valid:
        return None, Response(
            {"detail": _INVITATION_EXPIRED_MSG},
            status=status.HTTP_410_GONE,
        )

    return invitation, None


class InvitationAcceptView(APIView):
    """
    GET  /api/v1/agencies/me/invitations/accept/?token=<hex>
    POST /api/v1/agencies/me/invitations/accept/

    Public endpoint (no auth required).

    GET:  Validate token, return invitation details for form pre-fill.
    POST: Validate token, create User, mark invitation consumed, write AuditLog.

    Requirements: 4.3, 4.4, 4.5, 4.9
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        """
        Task 4.2 — Validate token and return invitation details.
        Requirements: 4.3, 4.5
        """
        token_param = request.query_params.get("token", "").strip()
        invitation, error = _lookup_invitation(token_param)
        if error:
            return error

        return Response(
            {
                "email": invitation.email,
                "role": invitation.role,
                "agency_name": invitation.agency.legal_name,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        """
        Task 4.3 — Accept invitation and create user account.
        Requirements: 4.4, 4.9
        """
        data = request.data
        token_param = (data.get("token") or "").strip()
        password = data.get("password") or ""
        username = (data.get("username") or "").strip()

        if not password:
            return Response(
                {"detail": "Password is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invitation, error = _lookup_invitation(token_param)
        if error:
            return error

        # Check email uniqueness
        if User.objects.filter(email=invitation.email).exists():
            return Response(
                {"detail": "This email address is already associated with an account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Derive username if not provided
        if not username:
            base = invitation.email.split("@")[0]
            # Ensure uniqueness by appending a short random suffix if needed
            candidate = base
            if User.objects.filter(username=candidate).exists():
                candidate = f"{base}_{os.urandom(4).hex()}"
            username = candidate

        # Create the user
        user = User.objects.create_user(
            username=username,
            email=invitation.email,
            password=password,
            role=invitation.role,
        )
        user.is_active = True
        user.email_verified = True
        user.agency = invitation.agency
        user.save(update_fields=["is_active", "email_verified", "agency_id"])

        # Mark invitation as consumed
        invitation.consumed_at = timezone.now()
        invitation.save(update_fields=["consumed_at"])

        # Write AuditLog
        AuditLog.objects.create(
            event_type=EventType.INVITATION_ACCEPTED,
            user=user,
            affected_entity_type="Invitation",
            affected_entity_id=str(invitation.pk),
            data_snapshot={
                "email": invitation.email,
                "role": invitation.role,
                "agency_id": str(invitation.agency.agency_id),
                "new_user_id": user.pk,
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(
            {"message": "Account created successfully. You can now log in."},
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Task 4.5 — Agency Member List
# GET /api/v1/agencies/me/members/
# Requirements: 11.4
# ---------------------------------------------------------------------------

class AgencyMemberListView(APIView):
    """
    GET /api/v1/agencies/me/members/

    AGENCY_ADMIN only. Returns a list of active members scoped to the
    authenticated admin's agency.

    Requirements: 11.4
    """

    permission_classes = [IsAgencyAdmin]

    def get(self, request):
        agency = request.user.agency
        if agency is None:
            return Response(
                {"detail": "Your account is not associated with an agency."},
                status=status.HTTP_403_FORBIDDEN,
            )

        members = User.objects.filter(
            agency=agency,
            is_active=True,
        ).order_by("username")

        data = [
            {
                "id": member.pk,
                "name": member.username,
                "email": member.email,
                "role": member.role,
                "last_login": member.last_login.isoformat() if member.last_login else None,
            }
            for member in members
        ]

        return Response(data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Task 4.6 — Agency Member Deactivate
# PATCH /api/v1/agencies/me/members/<id>/deactivate/
# Requirements: 4.7, 4.8, 4.9
# ---------------------------------------------------------------------------

class AgencyMemberDeactivateView(APIView):
    """
    PATCH /api/v1/agencies/me/members/<id>/deactivate/

    AGENCY_ADMIN only. Deactivates a member of the admin's own agency:
    - Enforces same-agency constraint (403 if different agency)
    - Sets User.is_active = False
    - Blacklists all active JWT refresh tokens for that user
    - Writes MEMBER_DEACTIVATED AuditLog entry

    Requirements: 4.7, 4.8, 4.9
    """

    permission_classes = [IsAgencyAdmin]

    def patch(self, request, pk: int):
        agency = request.user.agency
        if agency is None:
            return Response(
                {"detail": "Your account is not associated with an agency."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            target_user = User.objects.select_related("agency").get(pk=pk)
        except User.DoesNotExist:
            return Response(
                {"detail": "User not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Requirement 4.8: same-agency constraint
        if target_user.agency_id != agency.pk:
            return Response(
                {"detail": "You can only deactivate members of your own agency."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Prevent self-deactivation
        if target_user.pk == request.user.pk:
            return Response(
                {"detail": "You cannot deactivate your own account."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Deactivate the user
        target_user.is_active = False
        target_user.save(update_fields=["is_active"])

        # Blacklist all active JWT refresh tokens (Requirement 4.7)
        _blacklist_user_tokens(target_user)

        # Write AuditLog
        AuditLog.objects.create(
            event_type=EventType.MEMBER_DEACTIVATED,
            user=request.user,
            affected_entity_type="User",
            affected_entity_id=str(target_user.pk),
            data_snapshot={
                "deactivated_user_id": target_user.pk,
                "deactivated_email": target_user.email,
                "deactivated_role": target_user.role,
                "agency_id": str(agency.agency_id),
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(
            {"message": "Member deactivated."},
            status=status.HTTP_200_OK,
        )


def _blacklist_user_tokens(user: User) -> None:
    """
    Blacklist all outstanding (non-expired) JWT refresh tokens for the given user.
    Uses rest_framework_simplejwt.token_blacklist models.
    """
    try:
        from rest_framework_simplejwt.token_blacklist.models import (  # noqa: PLC0415
            BlacklistedToken,
            OutstandingToken,
        )

        outstanding = OutstandingToken.objects.filter(user=user)
        for token in outstanding:
            BlacklistedToken.objects.get_or_create(token=token)

        logger.info(
            "Blacklisted %d JWT refresh token(s) for user pk=%d.",
            outstanding.count(),
            user.pk,
        )
    except Exception as exc:
        logger.error(
            "Failed to blacklist JWT tokens for user pk=%d: %s",
            user.pk,
            exc,
        )


# ---------------------------------------------------------------------------
# Task 5.1 & 5.2 — Agency Profile (GET + PATCH)
# GET  /api/v1/agencies/me/  — all agency roles
# PATCH /api/v1/agencies/me/ — AGENCY_ADMIN only
# Requirements: 11.1, 11.2, 11.3, 11.5
# ---------------------------------------------------------------------------

_PROFILE_FIELDS = ("contact_name", "contact_email", "ministry")
_IMMUTABLE_FIELDS = ("gstin",)


class AgencyProfileView(APIView):
    """
    GET  /api/v1/agencies/me/
        All agency roles (AGENCY_ADMIN, AGENCY_OFFICER, REVIEWER).
        Returns the agency profile for the authenticated user's agency.
        Requirements: 11.1, 11.5

    PATCH /api/v1/agencies/me/
        AGENCY_ADMIN only.
        Allows updating contact_name, contact_email, ministry.
        Rejects GSTIN updates with HTTP 400.
        Writes AGENCY_STATUS_CHANGED AuditLog entry with field diffs.
        Requirements: 11.1, 11.2, 11.3
    """

    def get_permissions(self):
        if self.request.method == "PATCH":
            return [IsAgencyAdmin()]
        return [IsAgencyRole()]

    def _profile_data(self, agency) -> dict:
        return {
            "legal_name": agency.legal_name,
            "gstin": agency.gstin,
            "ministry": agency.ministry,
            "contact_name": agency.contact_name,
            "contact_email": agency.contact_email,
            "status": agency.status,
            "created_at": agency.created_at.isoformat(),
        }

    def get(self, request):
        """Task 5.1 — Return agency profile for all agency roles."""
        agency = request.user.agency
        if agency is None:
            return Response(
                {"detail": "Your account is not associated with an agency."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(self._profile_data(agency), status=status.HTTP_200_OK)

    def patch(self, request):
        """Task 5.2 — Update agency profile (AGENCY_ADMIN only)."""
        agency = request.user.agency
        if agency is None:
            return Response(
                {"detail": "Your account is not associated with an agency."},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data

        # Requirement 11.2: reject GSTIN update attempts
        if "gstin" in data:
            return Response(
                {"detail": "GSTIN cannot be modified after registration."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Collect only the allowed mutable fields that were actually provided
        updates = {}
        for field in _PROFILE_FIELDS:
            if field in data:
                value = data[field]
                if not isinstance(value, str) or not value.strip():
                    return Response(
                        {"detail": f"'{field}' must be a non-empty string."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                updates[field] = value.strip()

        if not updates:
            return Response(
                {"detail": "No updatable fields provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Requirement 11.3: capture previous values for audit diff
        previous_values = {field: getattr(agency, field) for field in updates}

        # Apply updates
        for field, value in updates.items():
            setattr(agency, field, value)
        agency.save(update_fields=list(updates.keys()))

        # Requirement 11.3: write AGENCY_STATUS_CHANGED AuditLog with field diffs
        field_diffs = {
            field: {"previous": previous_values[field], "new": updates[field]}
            for field in updates
        }
        AuditLog.objects.create(
            event_type=EventType.AGENCY_STATUS_CHANGED,
            user=request.user,
            affected_entity_type="Agency",
            affected_entity_id=str(agency.agency_id),
            data_snapshot={
                "action": "profile_updated",
                "changes": field_diffs,
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(self._profile_data(agency), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Pagination helper
# ---------------------------------------------------------------------------

class TenderPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

def _fraud_score_data(submission):
    """
    Return fraud score and risk badge data for a TenderSubmission.
    Reads from the linked Tender's FraudRiskScore if available.
    """
    score = None
    risk_badge = None

    if submission.tender_id is not None:
        try:
            frs = submission.tender.fraudriskscore
            score = float(frs.score)
            if score < 40:
                risk_badge = "green"
            elif score < 70:
                risk_badge = "amber"
            else:
                risk_badge = "red"
        except Exception:
            pass

    return {"fraud_risk_score": score, "risk_badge": risk_badge}


def _submission_to_dict(submission, include_agency=False):
    """Serialise a TenderSubmission to a dict for API responses."""
    data = {
        "id": submission.pk,
        "tender_ref": submission.tender_ref,
        "title": submission.title,
        "category": submission.category,
        "estimated_value": str(submission.estimated_value),
        "submission_deadline": submission.submission_deadline.isoformat(),
        "publication_date": (
            submission.publication_date.isoformat() if submission.publication_date else None
        ),
        "buyer_name": submission.buyer_name,
        "spec_text": submission.spec_text,
        "status": submission.status,
        "review_note": submission.review_note,
        "submitted_by": submission.submitted_by_id,
        "created_at": submission.created_at.isoformat(),
        "updated_at": submission.updated_at.isoformat(),
    }
    data.update(_fraud_score_data(submission))

    if include_agency:
        data["agency_id"] = str(submission.agency.agency_id)
        data["agency_name"] = submission.agency.legal_name

    return data


# ---------------------------------------------------------------------------
# Task 6.1 & 6.2 — Agency Tender List (GET + POST)
# GET  /api/v1/agencies/me/tenders/
# POST /api/v1/agencies/me/tenders/
# Requirements: 5.1, 5.3, 5.6, 5.7, 6.1-6.4, 6.11, 6.12, 8.2
# ---------------------------------------------------------------------------

_ALLOWED_ORDERINGS = {
    "created_at": "created_at",
    "-created_at": "-created_at",
    "estimated_value": "estimated_value",
    "-estimated_value": "-estimated_value",
    # fraud_risk_score ordering is handled in Python after fetching (no DB column)
    "fraud_risk_score": None,
    "-fraud_risk_score": None,
}

_REQUIRED_TENDER_FIELDS = [
    "tender_ref",
    "title",
    "category",
    "estimated_value",
    "submission_deadline",
    "buyer_name",
]


class AgencyTenderListView(APIView):
    """
    GET  /api/v1/agencies/me/tenders/
        All agency roles (IsAgencyRole).
        Returns paginated TenderSubmission list scoped to user's agency.
        Supports filters: status, category, date_from, date_to.
        Supports sort: ordering query param.
        Requirements: 5.1, 5.3, 5.6, 5.7, 8.2

    POST /api/v1/agencies/me/tenders/
        AGENCY_ADMIN or AGENCY_OFFICER (IsAgencyOfficerOrAdmin).
        Creates a TenderSubmission with status DRAFT.
        Requirements: 6.1, 6.2, 6.3, 6.4, 6.11, 6.12
    """

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAgencyOfficerOrAdmin()]
        return [IsAgencyRole()]

    def get(self, request):
        """Task 6.1 -- Paginated agency-scoped tender list with filters and sorting."""
        agency_id = request.user.agency_id
        if not agency_id:
            return Response(
                {"detail": "Your account is not associated with an agency."},
                status=status.HTTP_403_FORBIDDEN,
            )

        qs = TenderSubmission.objects.for_agency(agency_id).select_related(
            "agency", "tender__fraudriskscore"
        )

        # --- Filters ---
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        category_filter = request.query_params.get("category")
        if category_filter:
            qs = qs.filter(category__iexact=category_filter)

        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        # --- Ordering ---
        ordering_param = request.query_params.get("ordering", "-created_at")
        fraud_score_sort = None

        if ordering_param in ("fraud_risk_score", "-fraud_risk_score"):
            # Sort by fraud score in Python after fetching
            fraud_score_sort = ordering_param
            qs = qs.order_by("-created_at")
        elif ordering_param in _ALLOWED_ORDERINGS:
            db_ordering = _ALLOWED_ORDERINGS[ordering_param]
            if db_ordering:
                qs = qs.order_by(db_ordering)
        else:
            qs = qs.order_by("-created_at")

        # --- Pagination ---
        paginator = TenderPagination()
        page = paginator.paginate_queryset(qs, request)
        results = [_submission_to_dict(s) for s in page]

        # Apply fraud score sort in Python if needed
        if fraud_score_sort:
            reverse = fraud_score_sort.startswith("-")
            results.sort(
                key=lambda d: (d["fraud_risk_score"] is None, d["fraud_risk_score"] or 0),
                reverse=reverse,
            )

        return paginator.get_paginated_response(results)

    def post(self, request):
        """Task 6.2 -- Create a new TenderSubmission with status DRAFT."""
        agency = request.user.agency
        if agency is None:
            return Response(
                {"detail": "Your account is not associated with an agency."},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data

        # --- Required field validation ---
        missing = [f for f in _REQUIRED_TENDER_FIELDS if not str(data.get(f, "")).strip()]
        if missing:
            return Response(
                {"detail": "Missing required fields.", "missing_fields": missing},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- estimated_value: positive decimal with <= 2 decimal places ---
        try:
            estimated_value = Decimal(str(data["estimated_value"]))
        except (InvalidOperation, TypeError):
            return Response(
                {"detail": "estimated_value must be a valid decimal number."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if estimated_value <= 0:
            return Response(
                {"detail": "estimated_value must be a positive number."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Check <= 2 decimal places
        sign, digits, exponent = estimated_value.as_tuple()
        if isinstance(exponent, int) and exponent < -2:
            return Response(
                {"detail": "estimated_value must have at most 2 decimal places."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- submission_deadline: must be in the future ---
        from django.utils.dateparse import parse_datetime  # noqa: PLC0415
        try:
            submission_deadline = parse_datetime(str(data["submission_deadline"]))
            if submission_deadline is None:
                raise ValueError("unparseable")
        except (ValueError, TypeError):
            return Response(
                {"detail": "submission_deadline must be a valid ISO 8601 datetime."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if submission_deadline <= timezone.now():
            return Response(
                {"detail": "Submission deadline must be in the future."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Optional publication_date ---
        publication_date = None
        if data.get("publication_date"):
            from django.utils.dateparse import parse_datetime as _pd  # noqa: PLC0415
            publication_date = _pd(str(data["publication_date"]))

        # --- Sanitise text inputs (Requirement 6.11) ---
        title = bleach_clean(str(data["title"]).strip())
        buyer_name = bleach_clean(str(data["buyer_name"]).strip())
        spec_text = bleach_clean(str(data.get("spec_text", "") or ""))

        # --- Create TenderSubmission ---
        submission = TenderSubmission.objects.create(
            agency=agency,
            submitted_by=request.user,
            tender_ref=str(data["tender_ref"]).strip(),
            title=title,
            category=str(data["category"]).strip(),
            estimated_value=estimated_value,
            submission_deadline=submission_deadline,
            publication_date=publication_date,
            buyer_name=buyer_name,
            spec_text=spec_text,
            status=SubmissionStatus.DRAFT,
        )

        # --- Write TENDER_SUBMITTED AuditLog entry (Requirement 6.12) ---
        AuditLog.objects.create(
            event_type=EventType.TENDER_SUBMITTED,
            user=request.user,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(submission.pk),
            data_snapshot={
                "action": "created",
                "tender_ref": submission.tender_ref,
                "title": submission.title,
                "agency_id": str(agency.agency_id),
                "status": submission.status,
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(_submission_to_dict(submission), status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------------------
# Task 6.3, 6.4, 6.5 -- Agency Tender Detail (GET + PATCH + DELETE)
# GET    /api/v1/agencies/me/tenders/<id>/
# PATCH  /api/v1/agencies/me/tenders/<id>/
# DELETE /api/v1/agencies/me/tenders/<id>/
# Requirements: 5.3, 5.4, 6.8, 6.9, 6.10, 6.11, 6.12, 8.2
# ---------------------------------------------------------------------------

_EDITABLE_TENDER_FIELDS = [
    "tender_ref",
    "title",
    "category",
    "estimated_value",
    "submission_deadline",
    "publication_date",
    "buyer_name",
    "spec_text",
]


class AgencyTenderDetailView(APIView):
    """
    GET    /api/v1/agencies/me/tenders/<id>/
        All agency roles (IsAgencyRole).
        Returns tender detail with fraud score, red flag summary, and status.
        Enforces agency scoping via AgencyObjectPermission.
        Requirements: 5.3, 5.4, 8.2

    PATCH  /api/v1/agencies/me/tenders/<id>/
        AGENCY_ADMIN or AGENCY_OFFICER (IsAgencyOfficerOrAdmin).
        Enforces DRAFT-only editing (403 otherwise).
        Agency_Officer can only edit their own tenders.
        Requirements: 6.8, 6.9, 6.10, 6.11, 6.12

    DELETE /api/v1/agencies/me/tenders/<id>/
        AGENCY_ADMIN or AGENCY_OFFICER (IsAgencyOfficerOrAdmin).
        Enforces DRAFT-only deletion (403 otherwise).
        Agency_Officer can only delete their own tenders.
        Requirements: 6.8, 6.9, 6.10, 6.12
    """

    def get_permissions(self):
        if self.request.method in ("PATCH", "DELETE"):
            return [IsAgencyOfficerOrAdmin()]
        return [IsAgencyRole()]

    def _get_submission(self, request, pk):
        """
        Fetch a TenderSubmission, enforcing agency scoping.
        Returns (submission, error_response) -- one will be None.
        """
        agency_id = request.user.agency_id
        if not agency_id:
            return None, Response(
                {"detail": "Your account is not associated with an agency."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            submission = TenderSubmission.objects.select_related(
                "agency", "tender__fraudriskscore"
            ).get(pk=pk)
        except TenderSubmission.DoesNotExist:
            return None, Response(
                {"detail": "Not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Agency scoping check (Requirement 8.2)
        if submission.agency_id != agency_id:
            return None, Response(
                {"detail": "You do not have permission to access this resource."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return submission, None

    def get(self, request, pk):
        """Task 6.3 -- Return tender detail with fraud score and status."""
        submission, error = self._get_submission(request, pk)
        if error:
            return error

        data = _submission_to_dict(submission)

        # Include red flag summary if available
        red_flags = []
        if submission.tender_id is not None:
            try:
                flags = submission.tender.red_flags.values(
                    "rule_name", "severity", "description"
                )
                red_flags = list(flags)
            except Exception:
                pass
        data["red_flags"] = red_flags

        return Response(data, status=status.HTTP_200_OK)

    def patch(self, request, pk):
        """Task 6.4 -- Edit a DRAFT tender submission."""
        submission, error = self._get_submission(request, pk)
        if error:
            return error

        # Requirement 6.10: DRAFT-only editing
        if submission.status != SubmissionStatus.DRAFT:
            return Response(
                {"detail": "Only DRAFT tenders can be edited or deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Requirement 6.9: Agency_Officer can only edit their own tenders
        if (
            getattr(request.user, "role", None) == AGENCY_OFFICER
            and submission.submitted_by_id != request.user.pk
        ):
            return Response(
                {"detail": "Agency Officers can only edit their own tenders."},
                status=status.HTTP_403_FORBIDDEN,
            )

        data = request.data
        updates = {}

        for field in _EDITABLE_TENDER_FIELDS:
            if field not in data:
                continue
            value = data[field]

            if field == "estimated_value":
                try:
                    dec_val = Decimal(str(value))
                except (InvalidOperation, TypeError):
                    return Response(
                        {"detail": "estimated_value must be a valid decimal number."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if dec_val <= 0:
                    return Response(
                        {"detail": "estimated_value must be a positive number."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                sign, digits, exponent = dec_val.as_tuple()
                if isinstance(exponent, int) and exponent < -2:
                    return Response(
                        {"detail": "estimated_value must have at most 2 decimal places."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                updates[field] = dec_val

            elif field == "submission_deadline":
                from django.utils.dateparse import parse_datetime  # noqa: PLC0415
                parsed = parse_datetime(str(value))
                if parsed is None:
                    return Response(
                        {"detail": "submission_deadline must be a valid ISO 8601 datetime."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if parsed <= timezone.now():
                    return Response(
                        {"detail": "Submission deadline must be in the future."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                updates[field] = parsed

            elif field == "publication_date":
                if value:
                    from django.utils.dateparse import parse_datetime as _pd  # noqa: PLC0415
                    updates[field] = _pd(str(value))
                else:
                    updates[field] = None

            elif field in ("title", "buyer_name", "spec_text"):
                updates[field] = bleach_clean(str(value))

            else:
                updates[field] = str(value).strip()

        if not updates:
            return Response(
                {"detail": "No updatable fields provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for field, value in updates.items():
            setattr(submission, field, value)
        submission.save(update_fields=list(updates.keys()) + ["updated_at"])

        # Write AuditLog (Requirement 6.12)
        AuditLog.objects.create(
            event_type=EventType.TENDER_SUBMITTED,
            user=request.user,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(submission.pk),
            data_snapshot={
                "action": "edited",
                "tender_ref": submission.tender_ref,
                "agency_id": str(submission.agency.agency_id),
                "updated_fields": list(updates.keys()),
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(_submission_to_dict(submission), status=status.HTTP_200_OK)

    def delete(self, request, pk):
        """Task 6.5 -- Delete a DRAFT tender submission."""
        submission, error = self._get_submission(request, pk)
        if error:
            return error

        # Requirement 6.10: DRAFT-only deletion
        if submission.status != SubmissionStatus.DRAFT:
            return Response(
                {"detail": "Only DRAFT tenders can be edited or deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Requirement 6.9: Agency_Officer can only delete their own tenders
        if (
            getattr(request.user, "role", None) == AGENCY_OFFICER
            and submission.submitted_by_id != request.user.pk
        ):
            return Response(
                {"detail": "Agency Officers can only delete their own tenders."},
                status=status.HTTP_403_FORBIDDEN,
            )

        tender_ref = submission.tender_ref
        agency_id = str(submission.agency.agency_id)
        submission_pk = str(submission.pk)

        submission.delete()

        # Write AuditLog (Requirement 6.12)
        AuditLog.objects.create(
            event_type=EventType.TENDER_SUBMITTED,
            user=request.user,
            affected_entity_type="TenderSubmission",
            affected_entity_id=submission_pk,
            data_snapshot={
                "action": "deleted",
                "tender_ref": tender_ref,
                "agency_id": agency_id,
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Task 6.6 -- Agency Tender Submit
# POST /api/v1/agencies/me/tenders/<id>/submit/
# Requirements: 6.5, 6.12, 10.1
# ---------------------------------------------------------------------------

class AgencyTenderSubmitView(APIView):
    """
    POST /api/v1/agencies/me/tenders/<id>/submit/

    AGENCY_ADMIN or AGENCY_OFFICER.
    Transitions submission from DRAFT -> SUBMITTED.
    Creates a corresponding tenders.Tender record and links it.
    Enqueues score_agency_tender Celery task.
    Writes AuditLog entry.

    Requirements: 6.5, 6.12, 10.1
    """

    permission_classes = [IsAgencyOfficerOrAdmin]

    def post(self, request, pk):
        agency_id = request.user.agency_id
        if not agency_id:
            return Response(
                {"detail": "Your account is not associated with an agency."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            submission = TenderSubmission.objects.select_related("agency").get(pk=pk)
        except TenderSubmission.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        # Agency scoping
        if submission.agency_id != agency_id:
            return Response(
                {"detail": "You do not have permission to access this resource."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Attempt status transition DRAFT -> SUBMITTED
        try:
            submission.transition_to(SubmissionStatus.SUBMITTED, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Create a corresponding tenders.Tender record (Requirement 10.8)
        from tenders.models import Tender, TenderStatus  # noqa: PLC0415

        tender = Tender.objects.create(
            tender_id=submission.tender_ref,
            title=submission.title,
            category=submission.category,
            estimated_value=submission.estimated_value,
            submission_deadline=submission.submission_deadline,
            publication_date=submission.publication_date,
            buyer_id=str(submission.agency.agency_id),
            buyer_name=submission.buyer_name,
            spec_text=submission.spec_text,
            status=TenderStatus.ACTIVE,
        )

        # Link the Tender back to the TenderSubmission
        submission.tender = tender
        submission.save(update_fields=["tender_id", "updated_at"])

        # Enqueue score_agency_tender Celery task (Requirement 10.1)
        try:
            from agencies.tasks import score_agency_tender  # noqa: PLC0415
            score_agency_tender.delay(submission.pk)
        except Exception as exc:
            logger.warning(
                "Failed to enqueue score_agency_tender for submission %d: %s",
                submission.pk,
                exc,
            )

        # Write AuditLog (Requirement 6.12)
        AuditLog.objects.create(
            event_type=EventType.TENDER_SUBMITTED,
            user=request.user,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(submission.pk),
            data_snapshot={
                "action": "submitted",
                "tender_ref": submission.tender_ref,
                "tender_id": tender.pk,
                "agency_id": str(submission.agency.agency_id),
                "new_status": submission.status,
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(_submission_to_dict(submission), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Task 6.7 -- Cross-Agency Tender List (Government Auditor / Admin)
# GET /api/v1/agencies/tenders/
# Requirements: 12.1, 12.3, 12.5, 12.6
# ---------------------------------------------------------------------------

class CrossAgencyTenderListView(APIView):
    """
    GET /api/v1/agencies/tenders/

    GOVERNMENT_AUDITOR or ADMIN (IsGovernmentAuditorOrAdmin).
    Returns ALL TenderSubmission records across all agencies (no agency scoping).
    Includes agency_name and agency_id in each record.
    Writes GOV_AUDITOR_ACCESS AuditLog entry per request.

    Requirements: 12.1, 12.3, 12.5, 12.6
    """

    permission_classes = [IsGovernmentAuditorOrAdmin]

    def get(self, request):
        qs = TenderSubmission.objects.select_related(
            "agency", "tender__fraudriskscore"
        ).order_by("-created_at")

        # Support the same filters as the agency-scoped list
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        category_filter = request.query_params.get("category")
        if category_filter:
            qs = qs.filter(category__iexact=category_filter)

        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        paginator = TenderPagination()
        page = paginator.paginate_queryset(qs, request)
        results = [_submission_to_dict(s, include_agency=True) for s in page]

        # Write GOV_AUDITOR_ACCESS AuditLog entry (Requirement 12.6)
        AuditLog.objects.create(
            event_type=EventType.GOV_AUDITOR_ACCESS,
            user=request.user,
            affected_entity_type="TenderSubmission",
            affected_entity_id="",
            data_snapshot={
                "action": "cross_agency_list",
                "role": getattr(request.user, "role", None),
                "filters": {
                    "status": status_filter,
                    "category": category_filter,
                    "date_from": date_from,
                    "date_to": date_to,
                },
            },
            ip_address=_get_ip(request) or None,
        )

        return paginator.get_paginated_response(results)


# ---------------------------------------------------------------------------
# Task 6.8 -- Tender Clear View
# PATCH /api/v1/agencies/tenders/<id>/clear/
# Requirements: 7.5, 12.2
# ---------------------------------------------------------------------------

class TenderClearView(APIView):
    """
    PATCH /api/v1/agencies/tenders/<id>/clear/

    GOVERNMENT_AUDITOR or ADMIN.
    Calls submission.transition_to(CLEARED) with the review_note.
    Requires review_note of >= 10 characters (400 otherwise).
    Writes TENDER_CLEARED AuditLog entry with reviewer user ID and note.

    Requirements: 7.5, 12.2
    """

    permission_classes = [IsGovernmentAuditorOrAdmin]

    def patch(self, request, pk):
        try:
            submission = TenderSubmission.objects.select_related("agency").get(pk=pk)
        except TenderSubmission.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        review_note = str(request.data.get("review_note", "") or "").strip()
        if len(review_note) < 10:
            return Response(
                {"detail": "review_note must be at least 10 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Attempt transition to CLEARED
        try:
            submission.transition_to(
                SubmissionStatus.CLEARED,
                actor=request.user,
                review_note=review_note,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Write TENDER_CLEARED AuditLog entry (Requirement 7.5)
        AuditLog.objects.create(
            event_type=EventType.TENDER_CLEARED,
            user=request.user,
            affected_entity_type="TenderSubmission",
            affected_entity_id=str(submission.pk),
            data_snapshot={
                "reviewer_user_id": request.user.pk,
                "review_note": review_note,
                "tender_ref": submission.tender_ref,
                "agency_id": str(submission.agency.agency_id),
                "new_status": submission.status,
            },
            ip_address=_get_ip(request) or None,
        )

        return Response(_submission_to_dict(submission), status=status.HTTP_200_OK)
