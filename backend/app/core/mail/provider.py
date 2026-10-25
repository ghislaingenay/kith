"""Abstract interface all mail backends implement."""

from abc import ABC, abstractmethod


class Mailer(ABC):
    """Sends transactional email. Implementations must raise only
    `MailUnavailableError` (from `core/mail/exceptions.py`) on delivery
    failures — never leak provider-specific client exceptions across this
    boundary, so callers can catch one exception type."""

    @abstractmethod
    async def send(
        self, to: str, subject: str, body: str, html: str | None = None
    ) -> None:
        """Send an email to `to`: plain text, or plain text plus an HTML
        alternative when `html` is given."""
