"""Configuration and fixed budgets for the magic-link flow (ADR-0006)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MAGIC_LINK_TOKEN_TTL_SECONDS = 15 * 60
MAGIC_LINK_RATE_LIMIT_PER_HOUR = 5
MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS = 60 * 60


class MagicLinkSettings(BaseSettings):
    """Env-driven config for the link emailed to the visitor. Instantiated
    per-request in `auth/dependencies.py` (not module-level) so importing
    `auth.dependencies` — done by unrelated domains for `get_current_user` —
    doesn't require `MAGIC_LINK_VERIFY_URL` to be set."""

    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    verify_url: str = Field(validation_alias="MAGIC_LINK_VERIFY_URL")
