"""Turning a client-supplied filename into a Document's display name."""

import re

_MAX_NAME_LENGTH = 255
_FALLBACK_NAME = "document.pdf"
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")


def sanitize_display_name(filename: str) -> str:
    """The name shown in the app for an uploaded file: no directory part, no
    control characters, at most 255 characters. Display only — never used
    in a storage key."""
    name = re.split(r"[\\/]", filename)[-1]
    name = _CONTROL_CHARACTERS.sub("", name).strip()
    return name[:_MAX_NAME_LENGTH] or _FALLBACK_NAME
