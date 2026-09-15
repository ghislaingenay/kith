"""CORS configuration."""

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class CorsSettings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False)

    # `NoDecode` + the validator below: pydantic-settings otherwise tries to
    # JSON-decode a bare list[str] env var and raises on a plain
    # comma-separated string like "http://localhost:3000,http://foo".
    allowed_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=list, validation_alias="CORS_ALLOWED_ORIGINS"
    )

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value
