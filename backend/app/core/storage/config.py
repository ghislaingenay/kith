"""Configuration for storage provider selection (FR-5)."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

StorageProviderName = Literal["s3", "gcs", "r2", "minio"]


class StorageSettings(BaseSettings):
    """Env-driven storage config. `STORAGE_PROVIDER` picks the backend;
    `StorageProviderFactory` validates the fields required for that backend.
    """

    model_config = SettingsConfigDict(case_sensitive=False)

    provider: StorageProviderName = Field(validation_alias="STORAGE_PROVIDER")
    s3_bucket: str | None = Field(default=None, validation_alias="S3_BUCKET")
    s3_region: str | None = Field(default=None, validation_alias="S3_REGION")
    s3_endpoint: str | None = Field(default=None, validation_alias="S3_ENDPOINT")
    s3_public_endpoint: str | None = Field(
        default=None, validation_alias="S3_PUBLIC_ENDPOINT"
    )
    """Host to sign presigned URLs for when the browser reaches storage at a
    different address than the API does (e.g. `http://localhost:9000` vs the
    in-network `http://minio:9000`). Falls back to `S3_ENDPOINT` when unset."""
    public_base_url: str | None = Field(
        default=None, validation_alias="STORAGE_PUBLIC_BASE_URL"
    )
    """Optional CDN/public host to prefix public object URLs with (see
    `StorageProvider.upload(..., public=True)`). Falls back to a
    provider-computed URL (the S3 endpoint, or AWS's virtual-hosted-style
    URL) when unset."""
