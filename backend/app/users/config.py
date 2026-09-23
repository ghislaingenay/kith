"""Configuration for the users domain."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AvatarSettings(BaseSettings):
    """Env-driven: `AVATAR_PRESIGNED_URL_TTL_SECONDS` overrides how long a
    presigned avatar URL stays valid. Long enough for a page to sit open
    without the sidebar's image expiring; a fresh one is minted on every
    profile read regardless."""

    model_config = SettingsConfigDict(case_sensitive=False)

    presigned_url_ttl_seconds: int = Field(
        default=4 * 60 * 60, validation_alias="AVATAR_PRESIGNED_URL_TTL_SECONDS"
    )


# Every field has a default, so this can be a module-level singleton (same
# reasoning as auth/router.py's `_cookie_settings`).
avatar_settings = AvatarSettings()
