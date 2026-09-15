"""Configuration for cache provider selection."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CacheSettings(BaseSettings):
    """Env-driven cache config."""

    model_config = SettingsConfigDict(case_sensitive=False)

    redis_url: str = Field(validation_alias="REDIS_URL")
