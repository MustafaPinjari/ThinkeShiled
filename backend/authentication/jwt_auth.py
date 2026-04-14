"""
Custom JWT authentication backend.

Extends JWTAuthentication to write an AuditLog entry (EventType.JWT_INVALID_KEY)
whenever a token is rejected due to an unrecognised signing key, satisfying
Requirement 12.6.
"""

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


class AuditingJWTAuthentication(JWTAuthentication):
    """
    Drop-in replacement for JWTAuthentication that logs invalid-key events.

    When the token header is present but the token cannot be validated (e.g.
    signed with an unrecognised key), an AuditLog entry is written with
    event_type JWT_INVALID_KEY before re-raising the original exception so
    the DRF exception handler still returns HTTP 401.
    """

    def authenticate(self, request):
        # Extract the raw token from the Authorization header.
        # Returns None if the header is absent (unauthenticated request).
        header = self.get_header(request)
        if header is None:
            return None

        raw_token = self.get_raw_token(header)
        if raw_token is None:
            return None

        # Attempt validation; catch signature / key errors specifically.
        try:
            validated_token = self.get_validated_token(raw_token)
        except (InvalidToken, TokenError) as exc:
            # Only log when the failure looks like a signing-key mismatch.
            # simplejwt wraps the underlying jose error in the detail message.
            detail = str(exc).lower()
            if any(kw in detail for kw in ("signature", "key", "invalid", "decode")):
                self._write_invalid_key_audit(request, raw_token)
            raise

        return self.get_user(validated_token), validated_token

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_ip(request) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")

    @staticmethod
    def _write_invalid_key_audit(request, raw_token: bytes) -> None:
        """Write a JWT_INVALID_KEY AuditLog entry (best-effort; never raises)."""
        try:
            from audit.models import AuditLog, EventType

            # Decode the header/payload without verification to extract a
            # user hint for the audit record (may fail for malformed tokens).
            user_hint = ""
            try:
                import base64
                import json

                parts = raw_token.split(b".")
                if len(parts) >= 2:
                    padded = parts[1] + b"=" * (-len(parts[1]) % 4)
                    payload = json.loads(base64.urlsafe_b64decode(padded))
                    user_hint = str(payload.get("user_id", ""))
            except Exception:
                pass

            AuditLog.objects.create(
                event_type=EventType.JWT_INVALID_KEY,
                user=None,
                affected_entity_type="User",
                affected_entity_id=user_hint,
                data_snapshot={
                    "reason": "JWT presented with unrecognised or invalid signing key",
                    "path": request.path,
                    "method": request.method,
                },
                ip_address=AuditingJWTAuthentication._get_ip(request) or None,
            )
        except Exception:
            # Never let audit logging break the authentication flow.
            pass
