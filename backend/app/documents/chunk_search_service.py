"""Keyword search over a Tenant's Chunks."""

import uuid

from core.search.provider import ChunkHit, SearchIndex
from documents.repository import DocumentsRepository


class ChunkSearchService:
    def __init__(self, repository: DocumentsRepository, search_index: SearchIndex) -> None:
        self.repository = repository
        self.search_index = search_index

    async def search(
        self, *, tenant_id: uuid.UUID, query: str, limit: int = 10
    ) -> list[ChunkHit]:
        """Only Chunks of the Tenant's non-deleted Documents. The ids go to
        the index as a filter, so a deleted Document's Chunks, which stay in
        the index, never come back (ADR-0011)."""
        document_ids = await self.repository.list_live_document_ids(tenant_id=tenant_id)
        return await self.search_index.search_chunks(
            tenant_id=tenant_id, document_ids=document_ids, query=query, limit=limit
        )
