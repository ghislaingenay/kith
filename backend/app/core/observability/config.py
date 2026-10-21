"""Error and trace reporting to Sentry

Driven by `SENTRY_*` env vars; an empty `SENTRY_DSN`, or the default `local`
`SENTRY_ENVIRONMENT`, leaves Sentry off, so development and the smoke test
need no account. `configure_sentry()` is wired into `container.py` as a
Singleton (`container.sentry_configured()`), which the API and the ingest
worker call at import time, before the FastAPI app or the arq worker exists;
`lifespan` and arq's `on_startup` both run too late for the integrations.

No Tenant data leaves the process: no default PII, no request bodies, no
local variables in stack frames, no logs (as breadcrumbs, events or Sentry
logs), and `scrub_event` strips cookies, auth headers and email addresses
from whatever is left.
"""

import re
from collections.abc import Callable
from typing import Any

import sentry_sdk
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sentry_sdk.integrations.arq import ArqIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.types import Event, Hint

_LOCAL_ENVIRONMENT = "local"
_UNSAMPLED_PATHS = frozenset({"/health"})
_AUTH_HEADERS = frozenset(
    {"authorization", "proxy-authorization", "cookie", "set-cookie"}
)
_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_EMAIL_REPLACEMENT = "[email]"


class SentrySettings(BaseSettings):
    """Env-driven Sentry config."""

    # `populate_by_name=True`: same reason as `LoggingSettings` — field names
    # differ from their env var aliases.
    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    dsn: str = Field(default="", validation_alias="SENTRY_DSN")
    environment: str = Field(
        default=_LOCAL_ENVIRONMENT, validation_alias="SENTRY_ENVIRONMENT"
    )
    # The image's commit SHA, baked in by the backend Dockerfile's `GIT_SHA`.
    release: str | None = Field(default=None, validation_alias="SENTRY_RELEASE")
    traces_sample_rate: float = Field(
        default=0.1, ge=0.0, le=1.0, validation_alias="SENTRY_TRACES_SAMPLE_RATE"
    )

    @field_validator("release")
    @classmethod
    def _empty_release_is_none(cls, value: str | None) -> str | None:
        # An image built without `GIT_SHA` sets `SENTRY_RELEASE=""`.
        return value or None


def traces_sampler(rate: float) -> Callable[[dict[str, Any]], float]:
    """Sample every transaction at `rate`, except health checks, which Caddy
    and the uptime monitor hit often enough to drown out real traffic."""

    def sample(sampling_context: dict[str, Any]) -> float:
        path = sampling_context.get("asgi_scope", {}).get("path")
        return 0 if path in _UNSAMPLED_PATHS else rate

    return sample


def _scrub_emails(value: Any) -> Any:
    if isinstance(value, str):
        return _EMAIL_PATTERN.sub(_EMAIL_REPLACEMENT, value)
    if isinstance(value, dict):
        return {key: _scrub_emails(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub_emails(item) for item in value]
    return value


def scrub_event(event: Event, _hint: Hint) -> Event:
    """`before_send`: drop request bodies, cookies and auth headers, and mask
    every email address left anywhere in the event."""
    request: dict[str, Any] | None = event.get("request")
    if request:
        request.pop("data", None)
        request.pop("cookies", None)
        if headers := request.get("headers"):
            request["headers"] = {
                name: value
                for name, value in headers.items()
                if name.lower() not in _AUTH_HEADERS
            }
    if user := event.get("user"):
        user.pop("email", None)
    return _scrub_emails(event)


def configure_sentry(settings: SentrySettings) -> None:
    """Start Sentry process-wide, or do nothing without a DSN or in the local
    environment (a DSN copied into a dev `.env` stays silent). Called once via
    `container.sentry_configured()`."""
    if not settings.dsn or settings.environment == _LOCAL_ENVIRONMENT:
        return
    sentry_sdk.init(
        dsn=settings.dsn,
        environment=settings.environment,
        release=settings.release,
        traces_sampler=traces_sampler(settings.traces_sample_rate),
        before_send=scrub_event,
        # `before_send` skips traces, whose URLs and spans can carry emails too.
        before_send_transaction=scrub_event,
        send_default_pii=False,
        include_local_variables=False,
        max_request_body_size="never",
        enable_logs=False,
        integrations=[
            StarletteIntegration(),
            FastApiIntegration(),
            ArqIntegration(),
            # Logs stay local: no breadcrumbs, no error-log events.
            LoggingIntegration(level=None, event_level=None, sentry_logs_level=None),
        ],
    )
