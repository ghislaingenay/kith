"""Provider-agnostic exceptions for the mail abstraction."""


class MailError(Exception):
    """Base exception for all mailer provider failures."""


class MailUnavailableError(MailError):
    """Raised when the mail backend cannot be reached (connection failure, timeout)."""
