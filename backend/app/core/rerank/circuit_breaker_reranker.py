"""A `Reranker` that sends every request through one circuit breaker
(ADR-0013's pattern, ADR-0015), so a reranker that is down costs at most one
failed call per breaker cycle instead of one per Ask. The breaker is
injected; the composition root decides which errors count as failures."""

from collections.abc import Sequence

from core.circuit_breaker.breaker import CircuitBreaker
from core.rerank.provider import Reranker, RerankResult


class CircuitBreakerReranker(Reranker):
    def __init__(self, reranker: Reranker, breaker: CircuitBreaker) -> None:
        self._reranker = reranker
        self._breaker = breaker

    async def rerank(self, query: str, texts: Sequence[str]) -> RerankResult:
        return await self._breaker.call(lambda: self._reranker.rerank(query, texts))
