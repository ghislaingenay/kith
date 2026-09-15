"""Structured logging configuration (structlog)

Configures JSON logs in production and human-readable console logs in local
development, driven by `LOG_LEVEL`/`LOG_FORMAT` env vars. `configure_logging()`
is wired into `container.py` as a Singleton (`container.logging_configured()`),
matching the composition root's existing eager-init pattern for
`storage_provider`/`cache_provider`/`db_engine`/`job_queue` — `main.py`'s
`lifespan` calls it before anything else so structlog is configured before
any request or log line. Domain modules get their logger via `setup_logger()`
in place of stdlib's `logging.getLogger(__name__)`.
"""

import logging
from typing import Literal

import structlog
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ALLOWED_LEVELS = ("DEBUG", "INFO", "WARNING", "WARN", "ERROR", "CRITICAL")


class LoggingSettings(BaseSettings):
    """Env-driven logging config."""

    # `populate_by_name=True`: mirrors `dedup.config.DedupSettings` — field
    # names (`level`, `format`) differ from their env var aliases
    # (`LOG_LEVEL`, `LOG_FORMAT`), so both must be accepted for tests to
    # construct this by plain field name.
    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    format: Literal["json", "console"] = Field(
        default="json", validation_alias="LOG_FORMAT"
    )

    @field_validator("level")
    @classmethod
    def _validate_level(cls, value: str) -> str:
        level = value.upper()
        if level not in _ALLOWED_LEVELS:
            raise ValueError(
                f"Invalid LOG_LEVEL '{value}'. Expected one of: {', '.join(_ALLOWED_LEVELS)}"
            )
        return level


def _uppercase_level(
    _logger: object, _method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    # structlog's `add_log_level` emits lowercase ("info", "error"); FR-1's
    # schema example uses uppercase ("INFO", "ERROR").
    event_dict["level"] = event_dict["level"].upper()
    return event_dict


def configure_logging(settings: LoggingSettings) -> None:
    """Configure structlog process-wide. Called once via
    `container.logging_configured()`.

    `format="console"` renders human-readable output for local development;
    `format="json"` (production default) renders the JSON body FR-1's
    acceptance criteria describe. `merge_contextvars` is what makes
    `request_id` (bound by `RequestIDMiddleware`) appear on every log
    statement made within a request's async context, satisfying FR-2's
    "Logged: Included in every log statement".
    """
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.format == "console"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _uppercase_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.level.upper()]
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        # Deliberately NOT cache_logger_on_first_use=True: every domain module
        # calls `setup_logger(__name__)` at import time, which happens before
        # `container.logging_configured()` runs `configure_logging()` at
        # app/worker startup — caching on first log call would permanently
        # lock those loggers onto whatever structlog's pre-configuration
        # default renderer is, ignoring this configuration entirely.
        cache_logger_on_first_use=False,
    )
