"""
Validators for the agencies app.
"""

import re

from django.core.exceptions import ValidationError

# GSTIN pattern: 2 digits + 5 uppercase letters + 4 digits + 1 uppercase letter
#                + 1 alphanumeric (1-9 or A-Z) + literal 'Z' + 1 alphanumeric (0-9 or A-Z)
GSTIN_PATTERN = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$"
)


def validate_gstin(value: str) -> None:
    """
    Validate that *value* conforms to the Indian GSTIN format.

    Pattern: [0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}

    Raises:
        ValidationError: if *value* does not match the pattern.
    """
    if not GSTIN_PATTERN.match(value):
        raise ValidationError(
            "Enter a valid GSTIN. "
            "Expected format: 2 digits, 5 uppercase letters, 4 digits, "
            "1 uppercase letter, 1 alphanumeric (1-9/A-Z), 'Z', 1 alphanumeric.",
            code="invalid_gstin",
        )
