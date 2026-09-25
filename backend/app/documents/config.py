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
