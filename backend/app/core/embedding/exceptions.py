"""Errors raised by the embedding core module."""


class EmbeddingError(Exception):
    """The model rejected the request, and would reject it the same way again
    (for example a text over its limit)."""


class EmbeddingUnavailableError(EmbeddingError):
    """The model could not be reached, timed out, or is overloaded. The only
    failure worth retrying."""
