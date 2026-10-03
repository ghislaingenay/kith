"""Abstract interface the search store implements."""

import uuid
from abc import ABC, abstractmethod
from collections.abc import Sequence
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
    """One keyword-search result: enough to link to its Document and page."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    ordinal: int
    text: str
    score: float


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
    async def alias_exists(self) -> bool:
        """Whether the alias exists, without creating anything."""

    @abstractmethod
    async def replace_document_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: Sequence[ChunkDocument],
    ) -> None:
        """Make `chunks` the only Chunks the index holds for the Document: any
        earlier ones (a previous attempt's) are removed first. Searchable
        once this returns."""

    @abstractmethod
    async def search_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
        query: str,
        limit: int,
    ) -> list[ChunkHit]:
        """Keyword search over the Tenant's Chunks, restricted to the given
        Documents. The caller passes the Tenant's live Document ids, so a
        deleted Document's Chunks never appear even though they stay in the
        index."""

    @abstractmethod
    async def close(self) -> None:
        """Release the client's connections."""
