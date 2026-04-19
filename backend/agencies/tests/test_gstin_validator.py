"""
Unit tests for the GSTIN validator.

# Feature: agency-portal-rbac
# Requirement: 2.7

Tests at least 5 valid GSTINs and 5 invalid strings covering:
  - wrong total length (too short, too long)
  - lowercase letters where uppercase is required
  - missing literal 'Z' at position 13
  - invalid characters in specific positions
  - empty string
  - all-digit / all-alpha strings
"""

import pytest
from django.core.exceptions import ValidationError

from agencies.validators import validate_gstin


# ---------------------------------------------------------------------------
# Valid GSTINs
# Each string conforms to: [0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}
# ---------------------------------------------------------------------------

VALID_GSTINS = [
    # Real-world-style GSTINs (state code + PAN-derived structure + check digit)
    "27AAPFU0939F1ZV",  # Maharashtra, common test GSTIN
    "29ABCDE1234F1Z5",  # Karnataka
    "07AAAAA0000A1ZA",  # Delhi, alphanumeric check digit (A)
    "33BBBBB9999B9Z9",  # Tamil Nadu, digit '9' in position 12 and check digit
    "19CCCCC1111C1ZB",  # West Bengal, letter check digit (B)
    "01DDDDD2222D2ZC",  # Jammu & Kashmir, letter check digit (C)
    "36EEEEE3333E3Z0",  # Telangana, digit '0' as check digit
]


@pytest.mark.parametrize("gstin", VALID_GSTINS)
def test_valid_gstin_does_not_raise(gstin):
    """validate_gstin() must not raise for a correctly formatted GSTIN."""
    # Should complete without raising ValidationError
    validate_gstin(gstin)


# ---------------------------------------------------------------------------
# Invalid GSTINs — each entry is (gstin_string, description_of_defect)
# ---------------------------------------------------------------------------

INVALID_GSTINS = [
    # 1. Too short — 14 characters instead of 15
    ("27AAPFU0939F1Z", "too short (14 chars)"),
    # 2. Too long — 16 characters instead of 15
    ("27AAPFU0939F1ZV1", "too long (16 chars)"),
    # 3. Lowercase letters in the alpha-5 block (positions 2–6)
    ("27aapfu0939F1ZV", "lowercase in alpha-5 block"),
    # 4. Missing literal 'Z' at position 13 — replaced with 'X'
    ("27AAPFU0939F1XV", "missing 'Z' at position 13"),
    # 5. '0' in position 12 (the [1-9A-Z] slot) — '0' is not allowed there
    ("27AAPFU0939F0ZV", "digit '0' in [1-9A-Z] position"),
    # 6. Non-digit state code (positions 0–1) — letters instead of digits
    ("XXAAPFU0939F1ZV", "non-digit state code"),
    # 7. Special character in the middle
    ("27AAPFU093!F1ZV", "special character '!' in digit block"),
    # 8. Empty string
    ("", "empty string"),
    # 9. All digits — no alphabetic characters at all
    ("123456789012345", "all digits"),
    # 10. All uppercase letters — no digits at all
    ("AAAAAAAAAAAAAAA", "all uppercase letters"),
]


@pytest.mark.parametrize("gstin,description", INVALID_GSTINS)
def test_invalid_gstin_raises_validation_error(gstin, description):
    """validate_gstin() must raise ValidationError for every non-conforming string."""
    with pytest.raises(ValidationError) as exc_info:
        validate_gstin(gstin)

    # The error code must identify this as an invalid GSTIN
    assert exc_info.value.code == "invalid_gstin", (
        f"Expected error code 'invalid_gstin' for {description!r} ({gstin!r}), "
        f"got {exc_info.value.code!r}"
    )


# ---------------------------------------------------------------------------
# Edge-case: whitespace-padded strings are invalid
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gstin", [
    " 27AAPFU0939F1ZV",   # leading space
    "27AAPFU0939F1ZV ",   # trailing space
    "27AAPFU 0939F1ZV",   # internal space
])
def test_whitespace_padded_gstin_raises_validation_error(gstin):
    """Whitespace anywhere in the GSTIN string must be rejected."""
    with pytest.raises(ValidationError):
        validate_gstin(gstin)
