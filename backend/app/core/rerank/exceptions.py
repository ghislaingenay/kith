"""Errors raised by the rerank core module."""


class RerankConfigurationError(Exception):
    """The Rerank settings contradict each other. Not a `ValueError`, so
    pydantic raises it as is instead of wrapping it in a `ValidationError`."""
