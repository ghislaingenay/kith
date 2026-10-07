"""Against a real OpenSearch container: writing a vector onto a Chunk that is
already in the index (ADR-0014)."""

import uuid
from collections.abc import AsyncIterator

import pytest
from core.search.config import SearchSettings
from core.search.exceptions import SearchError, SearchUnavailableError
from core.search.opensearch_index import OpenSearchIndex
from core.search.provider import ChunkDocument
from opensearchpy import AsyncOpenSearch

_ALIAS = "kith-chunks"
_VECTOR_DIMENSION = 1024
_TENANT_ID = uuid.uuid4()
_OTHER_TENANT_ID = uuid.uuid4()


@pytest.fixture
async def client(_opensearch_url: str) -> AsyncIterator[AsyncOpenSearch]:
    async with AsyncOpenSearch(hosts=[_opensearch_url]) as opensearch_client:
        yield opensearch_client
        await opensearch_client.indices.delete(index="kith-chunks-*", ignore=[404])


@pytest.fixture
async def search_index(
    _opensearch_url: str, client: AsyncOpenSearch
) -> AsyncIterator[OpenSearchIndex]:
    index = OpenSearchIndex(SearchSettings(search_url=_opensearch_url))
    await index.ensure_index()
    yield index
    await index.close()


def _chunk(tenant_id: uuid.UUID, text: str) -> ChunkDocument:
    return ChunkDocument(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        document_id=uuid.uuid4(),
        page_number=1,
        ordinal=0,
        text=text,
    )


def _vector(value: float) -> list[float]:
    return [value] * _VECTOR_DIMENSION


async def _stored(client: AsyncOpenSearch, chunk: ChunkDocument) -> dict:
    return (await client.get(index=_ALIAS, id=str(chunk.id)))["_source"]


async def test_a_vector_lands_on_the_existing_chunk_and_it_stays_keyword_searchable(
    search_index: OpenSearchIndex, client: AsyncOpenSearch
) -> None:
    chunk = _chunk(_TENANT_ID, "quarterly revenue grew")
    await search_index.index_chunks([chunk])

    missing = await search_index.set_chunk_embeddings(
        tenant_id=_TENANT_ID, embeddings={chunk.id: _vector(0.5)}
    )

    assert missing == []
    stored = await _stored(client, chunk)
    assert stored["embedding"] == _vector(0.5)
    assert stored["text"] == "quarterly revenue grew"
    assert stored["tenant_id"] == str(_TENANT_ID)
    assert stored["document_id"] == str(chunk.document_id)
    hits = await search_index.search_chunks(
        tenant_id=_TENANT_ID, query="revenue", size=10
    )
    assert [hit.chunk_id for hit in hits] == [chunk.id]


async def test_a_vector_cannot_land_on_another_tenants_chunk(
    search_index: OpenSearchIndex, client: AsyncOpenSearch
) -> None:
    other_tenants_chunk = _chunk(_OTHER_TENANT_ID, "someone else's text")
    await search_index.index_chunks([other_tenants_chunk])

    missing = await search_index.set_chunk_embeddings(
        tenant_id=_TENANT_ID, embeddings={other_tenants_chunk.id: _vector(0.5)}
    )

    assert missing == [other_tenants_chunk.id]
    assert "embedding" not in await _stored(client, other_tenants_chunk)


async def test_a_chunk_missing_from_the_index_is_reported_and_the_rest_are_written(
    search_index: OpenSearchIndex, client: AsyncOpenSearch
) -> None:
    present = _chunk(_TENANT_ID, "present")
    absent_id = uuid.uuid4()
    await search_index.index_chunks([present])

    missing = await search_index.set_chunk_embeddings(
        tenant_id=_TENANT_ID,
        embeddings={absent_id: _vector(0.1), present.id: _vector(0.2)},
    )

    assert missing == [absent_id]
    assert (await _stored(client, present))["embedding"] == _vector(0.2)


async def test_writing_no_vectors_changes_nothing(
    search_index: OpenSearchIndex,
) -> None:
    assert (
        await search_index.set_chunk_embeddings(tenant_id=_TENANT_ID, embeddings={})
        == []
    )


async def test_a_vector_of_the_wrong_size_is_rejected(
    search_index: OpenSearchIndex,
) -> None:
    chunk = _chunk(_TENANT_ID, "text")
    await search_index.index_chunks([chunk])

    with pytest.raises(SearchError, match="rejected") as raised:
        await search_index.set_chunk_embeddings(
            tenant_id=_TENANT_ID, embeddings={chunk.id: [0.1, 0.2]}
        )

    assert not isinstance(raised.value, SearchUnavailableError)
