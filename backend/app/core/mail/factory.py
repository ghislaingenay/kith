"""Factory for instantiating a `Mailer` from configuration."""

from core.mail.config import MailSettings
from core.mail.provider import Mailer
from core.mail.smtp_provider import SMTPMailer


class MailerFactory:
    """Builds the configured `Mailer`."""

    @staticmethod
    def create(settings: MailSettings) -> Mailer:
        return SMTPMailer(
            host=settings.smtp_host,
            port=settings.smtp_port,
            from_address=settings.from_address,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
        )
