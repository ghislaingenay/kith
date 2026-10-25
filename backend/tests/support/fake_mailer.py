"""An in-memory fake `Mailer` for tests that need to assert an email was
(or wasn't) sent, and inspect its contents, without a real SMTP server."""

from typing import TypedDict

from core.mail.provider import Mailer


class SentMail(TypedDict):
    to: str
    subject: str
    body: str
    html: str | None


class FakeMailer(Mailer):
    def __init__(self) -> None:
        self.sent: list[SentMail] = []

    async def send(
        self, to: str, subject: str, body: str, html: str | None = None
    ) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body, "html": html})
