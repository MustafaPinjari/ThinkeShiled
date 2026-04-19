"""
Sanitisation helpers for the agencies app.

Used to sanitise user-supplied text fields (title, spec_text, buyer_name)
before persisting them to the database.
"""

import bleach


def bleach_clean(s: str) -> str:
    """Strip all HTML tags and attributes from *s* using bleach.

    Parameters
    ----------
    s:
        The input string to sanitise.

    Returns
    -------
    str
        The sanitised string with all HTML tags stripped.
    """
    return bleach.clean(s, tags=[], attributes={}, strip=True)
