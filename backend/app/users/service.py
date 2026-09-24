"""Users domain service: a User's own Profile."""

from auth.schemas import AuthenticatedUser
from core.logging import setup_logger
from core.storage.exceptions import StorageError
from core.storage.provider import StorageProvider
from users.avatar import (
    AVATAR_KEY_EXTENSIONS,
    CONTENT_TYPE_BY_EXTENSION,
    avatar_key,
    validate_avatar_upload,
)
from users.config import avatar_settings
from users.exceptions import ProfileNotFound
from users.models import Profile
from users.repository import ProfileRepository
from users.schemas import ProfileResponse

logger = setup_logger(__name__)


class ProfileService:
    def __init__(
        self, profile_repository: ProfileRepository, storage: StorageProvider
    ) -> None:
        self.profile_repository = profile_repository
        self.storage = storage

    async def update_name(
        self, user: AuthenticatedUser, name: str | None
    ) -> ProfileResponse:
        profile = await self._require_profile(user)
        profile.first_name = name
        profile = await self.profile_repository.update_profile(profile)
        return await self.to_response(user, profile)

    async def upload_avatar(
        self, user: AuthenticatedUser, *, content_type: str | None, data: bytes
    ) -> ProfileResponse:
        """Stores the image privately at the User's one fixed key and records
        that key on the Profile. Other-extension variants are deleted so a
        User only ever has one avatar object."""
        ext = validate_avatar_upload(content_type, len(data))
        key = avatar_key(user.id, ext)
        await self.storage.upload(
            key, data, content_type=CONTENT_TYPE_BY_EXTENSION[ext]
        )

        profile = await self._require_profile(user)
        profile.avatar_url = key
        profile = await self.profile_repository.update_profile(profile)

        for other_ext in AVATAR_KEY_EXTENSIONS:
            if other_ext != ext:
                await self.storage.delete(avatar_key(user.id, other_ext))
        return await self.to_response(user, profile)

    async def _require_profile(self, user: AuthenticatedUser) -> Profile:
        """Every User gets a Profile at signup (see
        `UserRepository.get_or_create_user`) — a mutation that finds none
        is a data-integrity bug, so it raises rather than silently
        creating one on the caller's behalf."""
        profile = await self.profile_repository.get_by_user_id(str(user.id))
        if profile is None:
            raise ProfileNotFound(user.id)
        return profile

    async def to_response(
        self, user: AuthenticatedUser, profile: Profile | None
    ) -> ProfileResponse:
        """Public so callers that already hold the Profile (e.g. `/me`, which
        loads it with the User) don't fetch it a second time."""
        # `profile.avatar_url` is the stored object key; only the response
        # carries the presigned URL, so the row is never written back with it.
        avatar_url = None
        if profile is not None and profile.avatar_url:
            try:
                avatar_url = await self.storage.generate_presigned_url(
                    profile.avatar_url,
                    "GET",
                    avatar_settings.presigned_url_ttl_seconds,
                )
            except StorageError as exc:
                # `/me` sits on the sign-in redirect path — a storage
                # outage degrades the avatar to missing rather than
                # failing sign-in.
                logger.warning(
                    f"Failed to presign avatar URL for user {user.id}: {exc}"
                )
        # The API's single display `name` is stored in `first_name`;
        # `last_name` is unused.
        return ProfileResponse(
            email=user.email,
            name=profile.first_name if profile else None,
            avatar_url=avatar_url,
        )
