"""Configuration for the documents domain."""

from pydantic import Field
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
