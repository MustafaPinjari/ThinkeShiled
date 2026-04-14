from rest_framework.throttling import UserRateThrottle


class AuthenticatedUserThrottle(UserRateThrottle):
    """100 requests per minute per authenticated user."""
    scope = "authenticated_user"
