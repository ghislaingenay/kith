from core.mail.config import MailSettings
from core.mail.factory import MailerFactory
from core.mail.smtp_provider import SMTPMailer


def test_create_returns_smtp_mailer() -> None:
    settings = MailSettings(
        smtp_host="localhost", smtp_port=1025, from_address="noreply@kith.dev"
    )

    mailer = MailerFactory.create(settings)

    assert isinstance(mailer, SMTPMailer)
