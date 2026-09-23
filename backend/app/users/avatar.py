"""Avatar upload rules and object-key layout.

Mirrors `tenants/logo.py`: `validate_avatar_upload` is pure and raises a
domain exception (never `HTTPException`), mapped to 422 in
`exception_handlers.py`.
"""

import uuid

from users.exceptions import InvalidAvatarUploadError

# content-type -> file extension used in the object key.
ALLOWED_AVATAR_CONTENT_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
}

# extension -> the canonical content-type stored with the object, so S3
# serves it as an image instead of the default `binary/octet-stream`.
CONTENT_TYPE_BY_EXTENSION: dict[str, str] = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}

MAX_AVATAR_BYTES = 2 * 1024 * 1024  # 2 MB

# Every extension an avatar can be stored under, so a re-upload in another
# format can remove the previous file. `jpeg` is never written here but a
# hand-uploaded `avatar.jpeg` must still be cleaned up.
AVATAR_KEY_EXTENSIONS: tuple[str, ...] = ("png", "jpg", "jpeg")


def avatar_key(user_id: uuid.UUID, ext: str) -> str:
    """Object key for a User's avatar — one fixed name per User, so each
    upload overwrites the previous."""
    return f"user/{user_id}/avatar/avatar.{ext}"


def validate_avatar_upload(content_type: str | None, size_bytes: int) -> str:
    """Return the file extension to store the avatar under, or raise
    `InvalidAvatarUploadError` if the type or size is not allowed."""
    ext = ALLOWED_AVATAR_CONTENT_TYPES.get((content_type or "").lower())
    if ext is None:
        raise InvalidAvatarUploadError("Avatar must be a JPEG or PNG image.")
    if size_bytes > MAX_AVATAR_BYTES:
        raise InvalidAvatarUploadError("Avatar image must be 2 MB or smaller.")
    if size_bytes == 0:
        raise InvalidAvatarUploadError("Avatar image is empty.")
    return ext
