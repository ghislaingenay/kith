"""Configuration for the search store."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchSettings(BaseSettings):
    """Env-driven search config."""

    model_config = SettingsConfigDict(case_sensitive=False)

    search_url: str = Field(validation_alias="SEARCH_URL")
    embedding_model_id: str = Field(
        default="voyage-4-large-1024", validation_alias="EMBEDDING_MODEL_ID"
    )
    """Part of the index name (ADR-0012): changing it means a new index."""
