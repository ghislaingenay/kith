"""Configuration for the retry handler's default backoff policy."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class RetrySettings(BaseSettings):
    """Env-driven retry defaults. Any field can be overridden per call via
    `RetryHandler.execute(...)` without touching the environment.
    """

    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    max_attempts: int = Field(default=3, validation_alias="RETRY_MAX_ATTEMPTS")
    base_delay: float = Field(default=0.5, validation_alias="RETRY_BASE_DELAY")
    max_delay: float = Field(default=10.0, validation_alias="RETRY_MAX_DELAY")
    jitter: bool = Field(default=True, validation_alias="RETRY_JITTER")
