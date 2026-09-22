class UserNotFound(Exception):
    """Raised when a user is not found in the database."""


class InvalidAvatarUploadError(Exception):
    """Raised when an uploaded avatar is the wrong content type, empty or too
    large. Mapped to HTTP 422 at the API boundary."""


class ProfileNotFound(Exception):
    """Raised when a User has no Profile row. Every User gets one created
    alongside it at signup (see `UserRepository.get_or_create_user`), so
    this means the invariant was violated — a data-integrity bug, never a
    client error, so it is mapped to HTTP 500 at the API boundary."""

    def __init__(self, user_id: object) -> None:
        self.user_id = user_id
        super().__init__(f"No Profile row for user_id={user_id!r}.")
