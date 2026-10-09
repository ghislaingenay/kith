"""A `Reranker` that gives up on a slow request (ADR-0015)."""

import asyncio
from collections.abc import Sequence

from core.rerank.exceptions import RerankUnavailableError
from core.rerank.provider import Reranker, RerankResult

RERANK_TIMEOUT_SECONDS = 5.0
"""How long Ask waits for the reranker before it keeps Retrieval's order, so
a slow reranker costs order instead of stalling the Ask."""


class TimeLimitedReranker(Reranker):
    """Gives up on a request that takes longer than `timeout_seconds`, as the
    reranker being unavailable, so the circuit breaker around it counts a slow
    reranker like a down one."""

    def __init__(self, reranker: Reranker, timeout_seconds: float) -> None:
        self._reranker = reranker
        self._timeout_seconds = timeout_seconds

    async def rerank(self, query: str, texts: Sequence[str]) -> RerankResult:
        try:
            async with asyncio.timeout(self._timeout_seconds):
                return await self._reranker.rerank(query, texts)
        except TimeoutError as error:
            raise RerankUnavailableError(
                f"Rerank took longer than {self._timeout_seconds}s"
            ) from error
