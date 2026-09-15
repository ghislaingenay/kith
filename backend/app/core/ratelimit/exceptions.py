"""Rate limit exceptions."""

from datetime import timedelta


class RateLimitError(Exception):
    """Base exception for rate limiting failures."""


class RateLimitUnavailableError(RateLimitError):
    """Raised when the rate limiter backend (Redis) cannot be reached."""


class RateLimitExceededError(RateLimitError):
    """Raised when a caller has exceeded its configured request budget."""

    def __init__(self, limit: int, remaining: int, retry_after: timedelta) -> None:
        self.limit = limit
        self.remaining = remaining
        self.retry_after = retry_after
        super().__init__("too many requests")
