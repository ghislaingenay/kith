"""Configuration for the answer model (ADR-0016)."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AnswerSettings(BaseSettings):
    """Env-driven config for the model that writes an Ask's Answer."""

    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    provider: Literal["openai"] = Field(
        default="openai", validation_alias="ANSWER_PROVIDER"
    )
    model: str = Field(
        default="gpt-6-luna", min_length=1, validation_alias="ANSWER_MODEL"
    )
    reasoning_effort: str = Field(
        default="low", min_length=1, validation_alias="ANSWER_REASONING_EFFORT"
    )
    max_output_tokens: int = Field(
        default=8_000,
        gt=0,
        description="Covers reasoning plus the visible Answer",
        validation_alias="ANSWER_MAX_OUTPUT_TOKENS",
    )
    # docker-compose passes an empty string when the variable is unset.
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
