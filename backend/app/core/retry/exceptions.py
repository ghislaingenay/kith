"""Exceptions for the retry handler."""


class RetryError(Exception):
    """Base exception for retry failures."""


class RetryExhaustedError(RetryError):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, attempts: int, last_exception: BaseException) -> None:
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"Retry exhausted after {attempts} attempt(s): {last_exception!r}"
        )
