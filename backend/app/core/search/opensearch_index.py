"""`SearchIndex` backed by OpenSearch."""

import uuid
from collections.abc import Sequence

from core.search.config import SearchSettings
from core.search.exceptions import ALREADY_EXISTS_ERROR, SearchError
from core.search.mapping import INDEX_ALIAS, index_body, versioned_index_name
from core.search.provider import ChunkDocument, ChunkHit, SearchIndex
from opensearchpy import AsyncOpenSearch, helpers
from opensearchpy.exceptions import RequestError


_MINIMUM_WORDS_MATCHED = "70%"


class OpenSearchIndex(SearchIndex):
    def __init__(self, settings: SearchSettings) -> None:
        self._client = AsyncOpenSearch(hosts=[settings.search_url])
        self._index_name = versioned_index_name(settings.embedding_model_id)

    @property
    def alias(self) -> str:
        return INDEX_ALIAS

    async def ensure_index(self) -> None:
        if await self.alias_exists():
            return
        try:
            await self._client.indices.create(index=self._index_name, body=index_body())
        except RequestError as error:
            # A concurrent run created it between the check and the create.
            if error.error != ALREADY_EXISTS_ERROR:
                raise

    async def alias_exists(self) -> bool:
        return await self._client.indices.exists_alias(name=INDEX_ALIAS)

    async def replace_document_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        document_id: uuid.UUID,
        chunks: Sequence[ChunkDocument],
    ) -> None:
        await self._client.delete_by_query(
            index=INDEX_ALIAS,
            body={
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"tenant_id": str(tenant_id)}},
                            {"term": {"document_id": str(document_id)}},
                        ]
                    }
                }
            },
            routing=str(tenant_id),
        )
        actions = [
            {
                "_op_type": "index",
                "_index": INDEX_ALIAS,
                "_id": str(chunk.id),
                "routing": str(chunk.tenant_id),
                "_source": {
                    "tenant_id": str(chunk.tenant_id),
                    "document_id": str(chunk.document_id),
                    "page_number": chunk.page_number,
                    "ordinal": chunk.ordinal,
                    "text": chunk.text,
                },
            }
            for chunk in chunks
        ]
        # Raises on any failed item, so the caller never marks a half-indexed
        # Document as indexed.
        try:
            await helpers.async_bulk(self._client, actions, refresh=True)
        except helpers.BulkIndexError as error:
            raise SearchError(f"Bulk indexing failed: {error.errors[:1]}") from error

    async def search_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        document_ids: Sequence[uuid.UUID],
        query: str,
        limit: int,
    ) -> list[ChunkHit]:
        if not document_ids:
            return []
        response = await self._client.search(
            index=INDEX_ALIAS,
            routing=str(tenant_id),
            body={
                "size": limit,
                "query": {
                    "bool": {
                        # Most of the words must match, in any order...
                        "must": [
                            {
                                "match": {
                                    "text": {
                                        "query": query,
                                        "minimum_should_match": _MINIMUM_WORDS_MATCHED,
                                    }
                                }
                            }
                        ],
                        # ...and the exact phrase ranks higher.
                        "should": [{"match_phrase": {"text": query}}],
                        "filter": [
                            {"term": {"tenant_id": str(tenant_id)}},
                            {
                                "terms": {
                                    "document_id": [str(document_id) for document_id in document_ids]
                                }
                            },
                        ],
                    }
                },
            },
        )
        return [
            ChunkHit(
                chunk_id=uuid.UUID(hit["_id"]),
                document_id=uuid.UUID(hit["_source"]["document_id"]),
                page_number=hit["_source"]["page_number"],
                ordinal=hit["_source"]["ordinal"],
                text=hit["_source"]["text"],
                score=hit["_score"],
            )
            for hit in response["hits"]["hits"]
        ]

    async def close(self) -> None:
        await self._client.close()
