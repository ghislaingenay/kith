"""Errors raised by the answer core module."""


class AnswerUnavailableError(Exception):
    """No answer model is configured, so no Ask can be answered."""
