from rest_framework.views import exception_handler
from rest_framework.response import Response


def custom_exception_handler(exc, context):
    """Return a consistent error envelope: {"error": {"code": ..., "message": ..., "details": ...}}"""
    response = exception_handler(exc, context)

    if response is not None:
        code = "ERROR"
        message = str(exc)
        details = {}

        status_code = response.status_code
        if status_code == 401:
            code = "TOKEN_EXPIRED" if "expired" in message.lower() else "INVALID_CREDENTIALS"
        elif status_code == 403:
            code = "PERMISSION_DENIED"
        elif status_code == 404:
            code = "NOT_FOUND"
        elif status_code == 422:
            code = "VALIDATION_ERROR"
        elif status_code == 429:
            code = "RATE_LIMITED"
        elif status_code == 400:
            code = "VALIDATION_ERROR"

        if isinstance(response.data, dict):
            details = response.data

        response.data = {
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        }

    return response
