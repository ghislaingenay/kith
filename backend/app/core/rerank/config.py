"""Configuration for Rerank (ADR-0004, ADR-0015)."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RerankSettings(BaseSettings):
    """Env-driven Rerank config for Ask's Retrieval; Search is never reranked."""

    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    enabled: bool = Field(default=True, validation_alias="RERANK_ENABLED")
    model: str = Field(
        default="rerank-3", min_length=1, validation_alias="RERANK_MODEL"
    )
    fetch_size: int = Field(
        default=50,
        gt=0,
        description="Hits asked of the search store, the candidates Rerank chooses from",
        validation_alias="RERANK_FETCH_SIZE",
    )
    result_limit: int = Field(
        default=5,
        gt=0,
        description="Chunks kept after Rerank, the ones an Ask cites",
        validation_alias="RERANK_RESULT_LIMIT",
    )

    @model_validator(mode="after")
    def _fetch_at_least_result_limit(self) -> "RerankSettings":
        if self.fetch_size < self.result_limit:
            raise ValueError("fetch size must be at least the result limit")
        return self
