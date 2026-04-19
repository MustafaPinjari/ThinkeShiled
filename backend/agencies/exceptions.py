"""
agencies/exceptions.py

Custom DRF exception handler that writes a PERMISSION_DENIED AuditLog entry
whenever an authenticated user receives an HTTP 403 response.

Register this handler in settings.py:
    REST_FRAMEWORK = {
        ...
        "EXCEPTION_HANDLER": "agencies.exceptions.agency_exception_handler",
    }

Requirements: 3.9
"""

from rest_framework.views import exception_handler


def _get_ip(request):
    """
    Extract the client IP address from the request.

    Checks the X-Forwarded-For header first (set by load balancers / proxies),
    then falls back to REMOTE_ADDR.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        # X-Forwarded-For may contain a comma-separated list; the first entry
        # is the originating client IP.
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def agency_exception_handler(exc, context):
    """
    DRF exception handler that delegates to the default handler and then, if
    the response is HTTP 403 and the request user is authenticated, writes a
    PERMISSION_DENIED AuditLog entry.

    The response is returned unchanged so normal DRF error serialisation is
    preserved.
    """
    response = exception_handler(exc, context)

    if response is not None and response.status_code == 403:
        request = context.get("request")
        if request and request.user.is_authenticated:
            # Lazy import to avoid circular dependency with the audit app.
            from audit.models import AuditLog, EventType  # noqa: PLC0415

            view = context.get("view")
            kwargs = context.get("kwargs") or {}

            AuditLog.objects.create(
                event_type=EventType.PERMISSION_DENIED,
                user=request.user,
                affected_entity_type=view.__class__.__name__ if view is not None else "",
                affected_entity_id=str(kwargs.get("pk", "")),
                data_snapshot={
                    "method": request.method,
                    "path": request.path,
                    "role": request.user.role,
                },
                ip_address=_get_ip(request),
            )

    return response
