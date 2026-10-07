"""Configuration for the documents domain."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class UploadSettings(BaseSettings):
    """Env-driven upload rules (ADR-0009)."""

    model_config = SettingsConfigDict(case_sensitive=False)

    max_file_bytes: int = Field(
        default=20 * 1024 * 1024, validation_alias="UPLOAD_MAX_FILE_BYTES"
    )
    presigned_url_ttl_seconds: int = Field(
        default=10 * 60, validation_alias="UPLOAD_PRESIGNED_URL_TTL_SECONDS"
    )
    max_pages: int = Field(default=100, validation_alias="UPLOAD_MAX_PAGES")
    max_documents: int = Field(default=20, validation_alias="UPLOAD_MAX_DOCUMENTS")
    """Documents Limit, the same for every Tenant until Limits are per Tenant."""
    max_storage_bytes: int = Field(
        default=100 * 1024 * 1024, validation_alias="UPLOAD_MAX_STORAGE_BYTES"
    )
    max_pending_per_user: int = Field(
        default=5, validation_alias="UPLOAD_MAX_PENDING_PER_USER"
    )
    max_allowed_per_hour: int = Field(
        default=30, description="Maximum allowed uploads per hour when the upload starts", validation_alias="UPLOAD_MAX_STARTS_PER_HOUR"
    )
    pending_expiry_seconds: int = Field(
        default=30 * 60, description="Time in seconds after which a pending upload expires", validation_alias="UPLOAD_PENDING_EXPIRY_SECONDS"
    )


class IngestionSettings(BaseSettings):
    """Env-driven ingestion rules (ADR-0010)."""

    model_config = SettingsConfigDict(case_sensitive=False)

    min_extraction_success_ratio: float = Field(
        default=0.8,
        ge=0,
        le=1,
        description="Minimum successful_pages / total_pages for a Document's extraction to count as a success",
        validation_alias="INGESTION_MIN_EXTRACTION_SUCCESS_RATIO",
    )
    chunk_size_tokens: int = Field(
        default=500,
        gt=0,
        description="Soft target size of a Chunk, in tokens (ADR-0011)",
        validation_alias="INGESTION_CHUNK_SIZE_TOKENS",
    )
    chunk_overlap_tokens: int = Field(
        default=50,
        ge=0,
        description="Tokens shared between consecutive Chunks of a page",
        validation_alias="INGESTION_CHUNK_OVERLAP_TOKENS",
    )

    index_batch_size: int = Field(
        default=100,
        gt=0,
        description="Chunks sent to the search store in one bulk request (ADR-0011)",
        validation_alias="INGESTION_INDEX_BATCH_SIZE",
    )

    embed_batch_token_cap: int = Field(
        default=100_000,
        gt=0,
        description="Voyage tokens sent to the embedding model in one request, kept under its 120K cap (ADR-0004)",
        validation_alias="INGESTION_EMBED_BATCH_TOKEN_CAP",
    )
    embed_batch_max_chunks: int = Field(
        default=1000,
        gt=0,
        description="Chunks sent to the embedding model in one request, the most it accepts",
        validation_alias="INGESTION_EMBED_BATCH_MAX_CHUNKS",
    )

    @model_validator(mode="after")
    def _overlap_smaller_than_size(self) -> "IngestionSettings":
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError("chunk overlap must be smaller than chunk size")
        return self


class RetrievalSettings(BaseSettings):
    """Env-driven Retrieval limits (ADR-0015)."""

    model_config = SettingsConfigDict(case_sensitive=False)

    fetch_size: int = Field(
        default=30,
        gt=0,
        description="Hits asked of the search store, more than are shown so deleted Documents' Chunks can be dropped",
        validation_alias="RETRIEVAL_FETCH_SIZE",
    )
    result_limit: int = Field(
        default=20,
        gt=0,
        description="Chunks kept after deleted Documents are dropped",
        validation_alias="RETRIEVAL_RESULT_LIMIT",
    )

    @model_validator(mode="after")
    def _fetch_at_least_result_limit(self) -> "RetrievalSettings":
        if self.fetch_size < self.result_limit:
            raise ValueError("fetch size must be at least the result limit")
        return self


class PreviewSettings(BaseSettings):
    """Env-driven rules for previewing a Document's PDF in the browser."""

    model_config = SettingsConfigDict(case_sensitive=False)

    preview_url_ttl_seconds: int = Field(
        default=5 * 60,
        gt=0,
        description="How long the presigned link the browser reads a Document's PDF from stays valid",
        validation_alias="PREVIEW_URL_TTL_SECONDS",
    )
