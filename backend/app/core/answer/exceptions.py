"""Errors raised by the answer core module."""


class AnswerError(Exception):
    """The answer model rejected the request, and would reject it the same way
    again (for example a bad key)."""


class AnswerUnavailableError(AnswerError):
    """No answer model is configured, or it could not be reached, timed out,
    or is overloaded."""
