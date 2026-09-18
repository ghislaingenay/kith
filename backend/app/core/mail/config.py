"""Configuration for the SMTP mailer."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MailSettings(BaseSettings):
    """Env-driven SMTP config. Mailpit (local/dev) needs only host/port/from —
    username, password and TLS are optional so the same settings shape covers
    a real SMTP provider in production."""

    model_config = SettingsConfigDict(case_sensitive=False, populate_by_name=True)

    smtp_host: str = Field(validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=1025, validation_alias="SMTP_PORT")
    smtp_username: str | None = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: str | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=False, validation_alias="SMTP_USE_TLS")
    from_address: str = Field(validation_alias="MAIL_FROM_ADDRESS")
