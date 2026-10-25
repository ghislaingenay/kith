"""Configuration and fixed budgets for the magic-link and session flows
(ADR-0006)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

MAGIC_LINK_TOKEN_TTL_SECONDS = 15 * 60
MAGIC_LINK_RATE_LIMIT_PER_HOUR = 5
# Stops a bot cycling addresses; a team signing up from one office fits.
MAGIC_LINK_IP_RATE_LIMIT_PER_HOUR = 20
MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS = 60 * 60

SESSION_TTL_SECONDS = 30 * 24 * 60 * 60
SESSION_COOKIE_NAME = "kith_session"


class MagicLinkSettings(BaseSettings):
    """Env-driven config for the link emailed to the visitor. Instantiated
    per-request in `auth/dependencies.py` (not module-level) so importing
    `auth.dependencies` — done by unrelated domains for `get_current_user` —
    doesn't require `MAGIC_LINK_VERIFY_URL` to be set."""

    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    verify_url: str = Field(validation_alias="MAGIC_LINK_VERIFY_URL")


class SessionCookieSettings(BaseSettings):
    """Env-driven flags for the session cookie (ADR-0006): `Secure` and the
    cookie's domain both come from environment so dev (plain HTTP, no
    shared parent domain) and prod (HTTPS, shared parent domain) differ only
    in config, never in code. Instantiated per-request in `auth/router.py`
    for the same reason as `MagicLinkSettings` above."""

    model_config = SettingsConfigDict(case_sensitive=False)

    cookie_secure: bool = Field(default=True, validation_alias="SESSION_COOKIE_SECURE")
    cookie_domain: str | None = Field(
        default=None, validation_alias="SESSION_COOKIE_DOMAIN"
    )
