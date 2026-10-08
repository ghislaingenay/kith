"""Factory for instantiating an `EmbeddingProvider` from configuration."""

from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.circuit_breaker_provider import CircuitBreakerEmbeddingProvider
from core.embedding.config import EmbeddingSettings
from core.embedding.provider import EmbeddingProvider
from core.embedding.voyage_provider import VoyageEmbeddingProvider
from pydantic import ValidationError


class EmbeddingProviderFactory:
    """Builds the configured `EmbeddingProvider`, behind the circuit breaker."""

    @staticmethod
    def create(
        settings: EmbeddingSettings, breaker: CircuitBreaker
    ) -> EmbeddingProvider:
        return CircuitBreakerEmbeddingProvider(
            VoyageEmbeddingProvider(settings), breaker
        )

    @staticmethod
    def create_for_queries(breaker: CircuitBreaker) -> EmbeddingProvider | None:
        """The provider the API embeds a Query with: a short request timeout,
        so a slow model degrades Search instead of stalling it. `None` when
        there is no Voyage API key, which the API tolerates (ADR-0015)."""
        try:
            settings = EmbeddingSettings()
        except ValidationError as error:
            # Only a missing key is tolerated; a bad timeout must still fail.
            if any(e["loc"] != ("VOYAGE_API_KEY",) for e in error.errors()):
                raise
            return None
        return CircuitBreakerEmbeddingProvider(
            VoyageEmbeddingProvider(settings, timeout=settings.query_timeout_seconds),
            breaker,
        )
