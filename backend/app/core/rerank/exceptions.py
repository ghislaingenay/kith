"""Errors raised by the rerank core module."""


class RerankConfigurationError(Exception):
    """The Rerank settings contradict each other. Not a `ValueError`, so
    pydantic raises it as is instead of wrapping it in a `ValidationError`."""


class RerankError(Exception):
    """The reranker rejected the request, and would reject it the same way
    again (for example a bad key)."""


class RerankUnavailableError(RerankError):
    """The reranker could not be reached, timed out, or is overloaded. The
    only failure the `rerank` circuit breaker counts."""
