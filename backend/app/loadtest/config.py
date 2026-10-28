"""Configuration for the load-test domain (ADR-0021)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LoadTestSettings(BaseSettings):
    """Env-driven. Off everywhere but the load-test VPS, whose `.env` sets
    `LOAD_TEST_ENABLED=true`; prod never does."""

    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    enabled: bool = Field(
        default=False,
        description="Allows creating Load Test Tenants, Users and Sessions",
        validation_alias="LOAD_TEST_ENABLED",
    )
