"""A `SearchIndex` that sends every call to the search store through one
circuit breaker (ADR-0011), so a store that is down is not hammered by every
job and batch. The breaker is injected; the composition root decides which
errors count as failures."""

import uuid
from collections.abc import Sequence

from core.circuit_breaker.breaker import CircuitBreaker
from core.search.provider import ChunkDocument, ChunkHit, SearchIndex


class CircuitBreakerSearchIndex(SearchIndex):
    def __init__(self, index: SearchIndex, breaker: CircuitBreaker) -> None:
        self._index = index
        self._breaker = breaker

    @property
    def alias(self) -> str:
        return self._index.alias

    async def ensure_index(self) -> None:
        await self._index.ensure_index()

    async def alias_exists(self) -> bool:
        return await self._index.alias_exists()

    async def delete_document_chunks(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        await self._breaker.call(
            lambda: self._index.delete_document_chunks(
                tenant_id=tenant_id, document_id=document_id
            )
        )

    async def index_chunks(self, chunks: Sequence[ChunkDocument]) -> None:
        await self._breaker.call(lambda: self._index.index_chunks(chunks))

    async def search_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
        query: str,
        limit: int,
    ) -> list[ChunkHit]:
        return await self._breaker.call(
            lambda: self._index.search_chunks(
                tenant_id=tenant_id,
                document_ids=document_ids,
                query=query,
                limit=limit,
            )
        )

    async def close(self) -> None:
        await self._index.close()
