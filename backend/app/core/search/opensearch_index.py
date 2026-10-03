"""`SearchIndex` backed by OpenSearch."""

import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from core.search.config import SearchSettings
from core.search.exceptions import (
    ALREADY_EXISTS_ERROR,
    SearchError,
    SearchUnavailableError,
)
from core.search.mapping import INDEX_ALIAS, index_body, versioned_index_name
from core.search.provider import ChunkDocument, ChunkHit, SearchIndex
from opensearchpy import AsyncOpenSearch, helpers
from opensearchpy.exceptions import OpenSearchException, RequestError


_MINIMUM_WORDS_MATCHED = "70%"


def _is_transient_status(status: object) -> bool:
    # A connection or timeout error carries no HTTP status (a string such as
    # "N/A"); a busy or failing store answers 429 or 5xx.
    return not isinstance(status, int) or status == 429 or status >= 500


def _is_transient(error: OpenSearchException) -> bool:
    if isinstance(error, helpers.BulkIndexError):
        return any(
            _is_transient_status(next(iter(item.values())).get("status"))
            for item in error.errors
        )
    return _is_transient_status(getattr(error, "status_code", None))


@contextmanager
def _store_errors(action: str) -> Iterator[None]:
    """Turns a failure of the store into the application's own errors: one
    worth retrying (`SearchUnavailableError`: unreachable, timing out,
    overloaded) or one that would fail the same way again (a rejected
    request, a mapping conflict), which must not trip the circuit breaker
    for every other Tenant."""
    try:
        yield
    except OpenSearchException as error:
        detail = (
            error.errors[:1] if isinstance(error, helpers.BulkIndexError) else error
        )
        if _is_transient(error):
            raise SearchUnavailableError(f"{action} failed: {detail}") from error
        raise SearchError(f"{action} was rejected: {detail}") from error


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

    async def delete_document_chunks(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        with _store_errors("Deleting Chunks"):
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

    async def index_chunks(self, chunks: Sequence[ChunkDocument]) -> None:
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
        # batch as indexed.
        with _store_errors("Bulk indexing"):
            await helpers.async_bulk(self._client, actions, refresh=True)

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
        with _store_errors("Searching Chunks"):
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
