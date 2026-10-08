"""Configuration for the embedding model."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingSettings(BaseSettings):
    """Env-driven embedding config."""

    model_config = SettingsConfigDict(case_sensitive=False)

    voyage_api_key: str = Field(min_length=1, validation_alias="VOYAGE_API_KEY")
    query_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        description="How long the API waits for a Query's embedding before Search falls back to keyword (ADR-0015)",
        validation_alias="EMBEDDING_QUERY_TIMEOUT_SECONDS",
    )
