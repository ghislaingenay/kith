"""SMTP-backed mail provider (works against Mailpit locally and any real
SMTP relay, including a provider like Resend's SMTP endpoint, in production).
"""

from email.message import EmailMessage

import aiosmtplib
from core.mail.exceptions import MailUnavailableError
from core.mail.provider import Mailer


class SMTPMailer(Mailer):
    """`Mailer` backed by `aiosmtplib`. Opens a new connection per send
    rather than holding one open — SMTP relays (Mailpit included) are fine
    with this, and it avoids a connection-lifecycle to manage across
    requests."""

    def __init__(
        self,
        host: str,
        port: int,
        from_address: str,
        username: str | None = None,
        password: str | None = None,
        use_tls: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._from_address = from_address
        self._username = username
        self._password = password
        self._use_tls = use_tls

    async def send(self, to: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from_address
        message["To"] = to
        message["Subject"] = subject
        message.set_content(body)

        try:
            await aiosmtplib.send(
                message,
                hostname=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
                use_tls=self._use_tls,
            )
        except aiosmtplib.SMTPException as exc:
            raise MailUnavailableError(f"SMTP send to {to!r} failed: {exc}") from exc
