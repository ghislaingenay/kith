"""Configuration for the circuit breaker's default thresholds."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CircuitBreakerSettings(BaseSettings):
    """Env-driven defaults, shared by every breaker built from them."""

    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    failure_threshold: int = Field(
        default=5, gt=0, validation_alias="CIRCUIT_BREAKER_FAILURE_THRESHOLD"
    )
    reset_timeout_seconds: float = Field(
        default=30, gt=0, validation_alias="CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS"
    )
