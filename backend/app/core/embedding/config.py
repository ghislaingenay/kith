"""Configuration for the embedding model."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingSettings(BaseSettings):
    """Env-driven embedding config."""

    model_config = SettingsConfigDict(case_sensitive=False)

    voyage_api_key: str = Field(validation_alias="VOYAGE_API_KEY")
