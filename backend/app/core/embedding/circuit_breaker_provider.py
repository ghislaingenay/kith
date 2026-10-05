"""An `EmbeddingProvider` that sends every request to the embedding model
through one circuit breaker (ADR-0013's pattern, ADR-0014), so a model that is
down is not hammered by every job and batch. The breaker is injected; the
composition root decides which errors count as failures."""

from collections.abc import Sequence

from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.provider import (
    EmbeddingInputType,
    EmbeddingProvider,
    EmbeddingResult,
)


class CircuitBreakerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, provider: EmbeddingProvider, breaker: CircuitBreaker) -> None:
        self._provider = provider
        self._breaker = breaker

    async def count_tokens(self, texts: Sequence[str]) -> list[int]:
        # The tokenizer runs here, not as a request to the model, so not guarded.
        return await self._provider.count_tokens(texts)

    async def embed(
        self, texts: Sequence[str], *, input_type: EmbeddingInputType
    ) -> EmbeddingResult:
        return await self._breaker.call(
            lambda: self._provider.embed(texts, input_type=input_type)
        )
