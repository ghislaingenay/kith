"""Factory for instantiating an `EmbeddingProvider` from configuration."""

from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.circuit_breaker_provider import CircuitBreakerEmbeddingProvider
from core.embedding.config import EmbeddingSettings
from core.embedding.provider import EmbeddingProvider
from core.embedding.voyage_provider import VoyageEmbeddingProvider


class EmbeddingProviderFactory:
    """Builds the configured `EmbeddingProvider`, behind the circuit breaker."""

    @staticmethod
    def create(
        settings: EmbeddingSettings,
        breaker: CircuitBreaker,
        timeout: float | None = None,
    ) -> EmbeddingProvider:
        """`timeout` caps each request to the model, in seconds."""
        return CircuitBreakerEmbeddingProvider(
            VoyageEmbeddingProvider(settings, timeout=timeout), breaker
        )
