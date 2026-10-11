"""Configuration for the credits domain (ADR-0017)."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class CreditSettings(BaseSettings):
    """Env-driven Credit Balance rules, in Credits (1 Credit = 1,000 tokens)."""

    model_config = SettingsConfigDict(case_sensitive=False)

    starting_grant_credits: int = Field(
        default=200,
        ge=0,
        description="Credits a Tenant created through onboarding starts with",
        validation_alias="STARTING_CREDIT_GRANT",
    )
    low_threshold_credits: int = Field(
        default=20,
        ge=0,
        description="Below this many Credits the balance shows as low",
        validation_alias="CREDIT_LOW_THRESHOLD",
    )
