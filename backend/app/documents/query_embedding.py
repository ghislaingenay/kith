"""The embedding provider Retrieval embeds a Query with (ADR-0015)."""

from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.config import EmbeddingSettings
from core.embedding.factory import EmbeddingProviderFactory
from core.embedding.provider import EmbeddingProvider
from pydantic import ValidationError

QUERY_EMBEDDING_TIMEOUT_SECONDS = 5.0
"""How long Search waits for a Query's embedding before it falls back to
keyword, so a slow model degrades Search instead of stalling it."""


def create_query_embedding_provider(
    breaker: CircuitBreaker,
) -> EmbeddingProvider | None:
    """`None` when there is no Voyage API key, which the API tolerates: every
    Search then runs keyword only."""
    try:
        settings = EmbeddingSettings()
    except ValidationError:
        return None
    return EmbeddingProviderFactory.create(
        settings, breaker, timeout=QUERY_EMBEDDING_TIMEOUT_SECONDS
    )
