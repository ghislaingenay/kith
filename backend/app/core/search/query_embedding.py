"""The embedding provider Search embeds a Query with (ADR-0015)."""

import asyncio
from collections.abc import Sequence

from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.circuit_breaker_provider import CircuitBreakerEmbeddingProvider
from core.embedding.config import EmbeddingSettings
from core.embedding.exceptions import EmbeddingUnavailableError
from core.embedding.provider import (
    EmbeddingInputType,
    EmbeddingProvider,
    EmbeddingResult,
)
from core.embedding.voyage_provider import VoyageEmbeddingProvider
from pydantic import ValidationError

QUERY_EMBEDDING_TIMEOUT_SECONDS = 5.0
"""How long Search waits for a Query's embedding before it falls back to
keyword, so a slow model degrades Search instead of stalling it."""


class TimeLimitedEmbeddingProvider(EmbeddingProvider):
    """Gives up on a request that takes longer than `timeout_seconds`, as the
    model being unavailable, so the circuit breaker around it counts a slow
    model like a down one."""

    def __init__(self, provider: EmbeddingProvider, timeout_seconds: float) -> None:
        self._provider = provider
        self._timeout_seconds = timeout_seconds

    async def count_tokens(self, texts: Sequence[str]) -> list[int]:
        return await self._provider.count_tokens(texts)

    async def embed(
        self, texts: Sequence[str], *, input_type: EmbeddingInputType
    ) -> EmbeddingResult:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._provider.embed(texts, input_type=input_type)
        except TimeoutError as error:
            raise EmbeddingUnavailableError(
                f"Embedding took longer than {self._timeout_seconds}s"
            ) from error


def create_query_embedding_provider(
    breaker: CircuitBreaker,
) -> EmbeddingProvider | None:
    """`None` when there is no Voyage API key, which the API tolerates: every
    Search then runs keyword only."""
    try:
        settings = EmbeddingSettings()
    except ValidationError:
        return None
    return CircuitBreakerEmbeddingProvider(
        TimeLimitedEmbeddingProvider(
            VoyageEmbeddingProvider(settings), QUERY_EMBEDDING_TIMEOUT_SECONDS
        ),
        breaker,
    )
