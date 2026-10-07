"""An in-memory `SearchIndex` stand-in. It records whether the index and
alias were created, and can be scripted to fail the way a search store that
is down does."""

import asyncio
import uuid
from collections.abc import Mapping, Sequence

from core.search.exceptions import SearchUnavailableError
from core.search.provider import ChunkDocument, ChunkHit


class FakeSearchIndex:
    def __init__(self, *, index_exists: bool = False) -> None:
        self.index_exists = index_exists
        self.ensure_calls = 0
        self.index_calls = 0
        self.delete_calls = 0
        self.indexed: list[ChunkDocument] = []
        self.embeddings: dict[uuid.UUID, list[float]] = {}
        """The vector written onto each indexed Chunk."""
        self.index_outcomes: list[bool] = []
        """What each `index_chunks` call does, in order: `True` works, `False`
        raises. Once used up, `down` decides."""
        self.down = False
        self.delete_down = False
        self.search_down = False
        self.mark_deleted_down = False
        self.deleted_document_ids: set[uuid.UUID] = set()
        """Documents whose Chunks `search_chunks` leaves out."""
        self.delay_seconds = 0.0
        """How long `delete_document_chunks` and `index_chunks` take before
        they answer, as a slow store does."""
        self.crash_with: Exception | None = None
        """Raised by `index_chunks` instead of anything else, to stand for a
        failure that is not the search store being unavailable."""

    @property
    def alias(self) -> str:
        return "kith-chunks"

    async def ensure_index(self) -> None:
        self.ensure_calls += 1
        self.index_exists = True

    async def alias_exists(self) -> bool:
        return self.index_exists

    async def delete_document_chunks(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        self.delete_calls += 1
        await asyncio.sleep(self.delay_seconds)
        if self.delete_down:
            raise SearchUnavailableError("fake search store is down")
        self.indexed = [c for c in self.indexed if c.document_id != document_id]

    async def mark_document_chunks_deleted(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        if self.mark_deleted_down:
            raise SearchUnavailableError("fake search store is down")
        self.deleted_document_ids.add(document_id)

    async def index_chunks(self, chunks: Sequence[ChunkDocument]) -> None:
        self.index_calls += 1
        await asyncio.sleep(self.delay_seconds)
        if self.crash_with is not None:
            raise self.crash_with
        works = self.index_outcomes.pop(0) if self.index_outcomes else not self.down
        if not works:
            raise SearchUnavailableError("fake search store is down")
        self.indexed.extend(chunks)

    async def set_chunk_embeddings(
        self,
        *,
        tenant_id: uuid.UUID,
        embeddings: Mapping[uuid.UUID, Sequence[float]],
    ) -> list[uuid.UUID]:
        tenant_chunk_ids = {c.id for c in self.indexed if c.tenant_id == tenant_id}
        missing = [id_ for id_ in embeddings if id_ not in tenant_chunk_ids]
        for id_, vector in embeddings.items():
            if id_ in tenant_chunk_ids:
                self.embeddings[id_] = list(vector)
        return missing

    async def search_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        query_vector: Sequence[float] | None = None,
        size: int,
    ) -> list[ChunkHit]:
        """Chunks of the Tenant containing any word of the Query, in the order
        they were indexed. A stand-in for ranking, which tests of real
        relevance leave to OpenSearch."""
        if self.search_down:
            raise SearchUnavailableError("fake search store is down")
        words = query.lower().split()
        return [
            ChunkHit(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                page_number=chunk.page_number,
                ordinal=chunk.ordinal,
                text=chunk.text,
                score=1.0,
                highlights=[chunk.text],
            )
            for chunk in self.indexed
            if chunk.tenant_id == tenant_id
            and chunk.document_id not in self.deleted_document_ids
            and any(word in chunk.text.lower() for word in words)
        ][:size]

    async def close(self) -> None:
        pass
