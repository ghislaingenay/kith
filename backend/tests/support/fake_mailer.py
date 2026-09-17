"""An in-memory fake `Mailer` for tests that need to assert an email was
(or wasn't) sent, and inspect its contents, without a real SMTP server."""

from core.mail.provider import Mailer


class FakeMailer(Mailer):
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, to: str, subject: str, body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "body": body})
