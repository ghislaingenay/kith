"""Tenant logo upload rules and object-key layout.

Kept out of `router.py` so the HTTP layer stays thin: `validate_logo_upload`
is pure and raises a domain exception (never `HTTPException`), mapped to 422
in `exception_handlers.py`.
"""

import uuid

from tenants.exceptions import InvalidLogoUploadError

# content-type -> file extension used in the object key.
ALLOWED_LOGO_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
}

MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB

# Every extension a tenant logo can be stored under. `jpeg` and `jpg` both
# map from `image/jpeg`; only `jpg` is ever written, but a hand-uploaded
# `logo.jpeg` must still be found/cleaned up.
LOGO_KEY_EXTENSIONS: tuple[str, ...] = ("png", "jpg", "jpeg")


def logo_key(tenant_id: uuid.UUID, ext: str) -> str:
    """S3 key for a tenant's logo — one fixed name per tenant, so each
    upload overwrites the previous."""
    return f"tenant/{tenant_id}/logo/logo.{ext}"


def validate_logo_upload(content_type: str | None, size_bytes: int) -> str:
    """Return the file extension to store the logo under, or raise
    `InvalidLogoUploadError` if the type or size is not allowed."""
    ext = ALLOWED_LOGO_CONTENT_TYPES.get((content_type or "").lower())
    if ext is None:
        raise InvalidLogoUploadError("Logo must be a JPEG or PNG image.")
    if size_bytes > MAX_LOGO_BYTES:
        raise InvalidLogoUploadError("Logo image must be 2 MB or smaller.")
    if size_bytes == 0:
        raise InvalidLogoUploadError("Logo image is empty.")
    return ext
