from datetime import timedelta

from django.contrib.auth import authenticate
from django.utils import timezone
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from audit.models import AuditLog, EventType
from authentication.tasks import send_lockout_email_task

LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATION_MINUTES = 10


def _get_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _write_audit(event_type, user, data_snapshot, ip_address):
    AuditLog.objects.create(
        event_type=event_type,
        user=user,
        affected_entity_type="User",
        affected_entity_id=str(user.id) if user else "",
        data_snapshot=data_snapshot,
        ip_address=ip_address or None,
    )


@method_decorator(ratelimit(key="ip", rate="10/m", block=True), name="post")
class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        ip = _get_ip(request)

        # Look up user to check lock status before authenticating
        from authentication.models import User
        try:
            user_obj = User.objects.get(username=username)
        except User.DoesNotExist:
            user_obj = None

        # Check account lock
        if user_obj and user_obj.is_locked():
            return Response(
                {
                    "detail": "Account locked.",
                    "locked_until": user_obj.locked_until.isoformat(),
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Authenticate
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # Success — reset counters
            user.failed_login_attempts = 0
            user.locked_until = None
            user.save(update_fields=["failed_login_attempts", "locked_until"])

            # Issue tokens
            refresh = RefreshToken.for_user(user)
            access = refresh.access_token
            expires_in = int(access.lifetime.total_seconds())

            _write_audit(EventType.USER_LOGIN, user, {"username": user.username}, ip)

            return Response(
                {
                    "access": str(access),
                    "refresh": str(refresh),
                    "expires_in": expires_in,
                    "role": user.role,
                },
                status=status.HTTP_200_OK,
            )

        # Failed authentication
        if user_obj:
            user_obj.failed_login_attempts += 1
            now = timezone.now()

            if user_obj.failed_login_attempts >= LOCKOUT_THRESHOLD:
                user_obj.locked_until = now + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
                user_obj.save(update_fields=["failed_login_attempts", "locked_until"])

                _write_audit(
                    EventType.USER_LOCKED,
                    user_obj,
                    {
                        "username": user_obj.username,
                        "locked_until": user_obj.locked_until.isoformat(),
                    },
                    ip,
                )
                send_lockout_email_task.delay(user_obj.id)
            else:
                user_obj.save(update_fields=["failed_login_attempts"])

            _write_audit(
                EventType.USER_LOGIN_FAILED,
                user_obj,
                {
                    "username": user_obj.username,
                    "failed_attempts": user_obj.failed_login_attempts,
                },
                ip,
            )

            return Response(
                {
                    "detail": "Invalid credentials.",
                    "failed_attempts": user_obj.failed_login_attempts,
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Unknown username — no user object to update
        return Response(
            {"detail": "Invalid credentials.", "failed_attempts": 0},
            status=status.HTTP_401_UNAUTHORIZED,
        )


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh", "")
        ip = _get_ip(request)

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {"detail": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _write_audit(
            EventType.USER_LOGOUT,
            request.user,
            {"username": request.user.username},
            ip,
        )

        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)
