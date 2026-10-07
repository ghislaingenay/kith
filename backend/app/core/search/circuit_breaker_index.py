"""A `SearchIndex` that sends every call to the search store through one
circuit breaker (ADR-0011, ADR-0013), so a store that is down is not hammered by every
job and batch. The breaker is injected; the composition root decides which
errors count as failures."""

import uuid
from collections.abc import Mapping, Sequence

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

    async def recreate_index(self) -> None:
        await self._index.recreate_index()

    async def update_mapping(self) -> None:
        await self._index.update_mapping()

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

    async def mark_document_chunks_deleted(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        await self._breaker.call(
            lambda: self._index.mark_document_chunks_deleted(
                tenant_id=tenant_id, document_id=document_id
            )
        )

    async def index_chunks(self, chunks: Sequence[ChunkDocument]) -> None:
        await self._breaker.call(lambda: self._index.index_chunks(chunks))

    async def set_chunk_embeddings(
        self,
        *,
        tenant_id: uuid.UUID,
        embeddings: Mapping[uuid.UUID, Sequence[float]],
    ) -> list[uuid.UUID]:
        return await self._breaker.call(
            lambda: self._index.set_chunk_embeddings(
                tenant_id=tenant_id, embeddings=embeddings
            )
        )

    async def search_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        query_vector: Sequence[float] | None = None,
        size: int,
    ) -> list[ChunkHit]:
        return await self._breaker.call(
            lambda: self._index.search_chunks(
                tenant_id=tenant_id,
                query=query,
                query_vector=query_vector,
                size=size,
            )
        )

    async def close(self) -> None:
        await self._index.close()
