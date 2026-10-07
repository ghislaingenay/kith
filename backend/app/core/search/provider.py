"""Abstract interface the search store implements."""

import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ChunkDocument:
    """A Chunk as the index stores it, under the id of its Postgres row. No
    vector until the embedding phase."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    ordinal: int
    text: str


@dataclass(frozen=True)
class ChunkHit:
    """One search result: enough to link to its Document and page, with the
    passages that matched. `highlights` are fragments of `text`, HTML-escaped,
    with each match wrapped in `<mark>`; empty when the store found none."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    ordinal: int
    text: str
    score: float
    highlights: list[str]


class SearchIndex(ABC):
    """The one place the application talks to the keyword and vector search
    store (ADR-0012)."""

    @property
    @abstractmethod
    def alias(self) -> str:
        """The alias the application reads and writes through."""

    @abstractmethod
    async def ensure_index(self) -> None:
        """Create the versioned index and its alias if they do not exist.
        Calling it again changes nothing."""

    @abstractmethod
    async def recreate_index(self) -> None:
        """Delete every Chunk by deleting the index with all its versions, then
        create it and its alias again, empty. For development."""

    @abstractmethod
    async def update_mapping(self) -> None:
        """Add to the existing index every field the current mapping has and
        the index lacks, keeping its Chunks. For development, when a field is
        added without a new index version; calling it again changes nothing.
        Raises `SearchUnavailableError` when the store cannot be reached."""

    @abstractmethod
    async def alias_exists(self) -> bool:
        """Whether the alias exists, without creating anything."""

    @abstractmethod
    async def delete_document_chunks(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """Remove every Chunk the index holds for the Document (a previous
        attempt's, before it is indexed again). Raises
        `SearchUnavailableError` when the store cannot be reached."""

    @abstractmethod
    async def mark_document_chunks_deleted(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """Flags every Chunk the index holds for the Document as deleted, so
        `search_chunks` stops returning them at once; the purge removes them
        later. Raises `SearchUnavailableError` when the store cannot be
        reached."""

    @abstractmethod
    async def index_chunks(self, chunks: Sequence[ChunkDocument]) -> None:
        """Bulk-index one batch of Chunks under their ids; searchable once
        this returns. Raises `SearchUnavailableError` when the store cannot
        be reached or rejects any of them."""

    @abstractmethod
    async def set_chunk_embeddings(
        self,
        *,
        tenant_id: uuid.UUID,
        embeddings: Mapping[uuid.UUID, Sequence[float]],
    ) -> list[uuid.UUID]:
        """Adds each vector to the Tenant's Chunk of that id already in the
        index, leaving its other fields untouched. Returns the ids the Tenant
        has no Chunk for (deleted meanwhile, or another Tenant's); those are
        reported, not raised. Raises `SearchUnavailableError` when the store
        cannot be reached, and `SearchError` when it rejects a vector."""

    @abstractmethod
    async def search_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        query_vector: Sequence[float] | None = None,
        size: int,
    ) -> list[ChunkHit]:
        """The Tenant's best-matching Chunks for the Query, best first, at
        most `size`. Only Chunks flagged as deleted are left out, besides the
        Tenant filter (ADR-0015); the caller still drops hits whose Document
        Postgres says is deleted, for the moment before the flag is set.
        Matches by keyword; `query_vector`, the Query's embedding, is for the
        meaning leg and not supported yet. Raises `SearchUnavailableError`
        when the store cannot be reached."""

    @abstractmethod
    async def close(self) -> None:
        """Release the client's connections."""
