"""Against a real OpenSearch container: Chunks flagged as deleted are left out
of a search (ADR-0015), without Postgres being asked."""

import uuid
from collections.abc import AsyncIterator

import pytest
from core.search.config import SearchSettings
from core.search.mapping import index_body, versioned_index_name
from core.search.opensearch_index import OpenSearchIndex
from core.search.provider import ChunkDocument
from opensearchpy import AsyncOpenSearch

_TENANT_ID = uuid.uuid4()
_OTHER_TENANT_ID = uuid.uuid4()


@pytest.fixture
async def search_index(_opensearch_url: str) -> AsyncIterator[OpenSearchIndex]:
    index = OpenSearchIndex(SearchSettings(search_url=_opensearch_url))
    await index.ensure_index()
    yield index
    await index.close()
    async with AsyncOpenSearch(hosts=[_opensearch_url]) as client:
        await client.indices.delete(index="kith-chunks-*", ignore=[404])


def _chunk(tenant_id: uuid.UUID, document_id: uuid.UUID, text: str) -> ChunkDocument:
    return ChunkDocument(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        document_id=document_id,
        page_number=1,
        ordinal=0,
        text=text,
    )


async def _found_ids(search_index: OpenSearchIndex, tenant_id: uuid.UUID) -> set:
    hits = await search_index.search_chunks(
        tenant_id=tenant_id, query="termination", size=10
    )
    return {hit.chunk_id for hit in hits}


async def test_a_flagged_documents_chunks_are_not_returned_and_others_still_are(
    search_index: OpenSearchIndex,
) -> None:
    deleted_document_id, live_document_id = uuid.uuid4(), uuid.uuid4()
    deleted_chunk = _chunk(_TENANT_ID, deleted_document_id, "termination clause")
    live_chunk = _chunk(_TENANT_ID, live_document_id, "termination in writing")
    await search_index.index_chunks([deleted_chunk, live_chunk])

    await search_index.mark_document_chunks_deleted(
        tenant_id=_TENANT_ID, document_id=deleted_document_id
    )

    assert await _found_ids(search_index, _TENANT_ID) == {live_chunk.id}


async def test_flagging_for_another_tenant_leaves_the_chunks_searchable(
    search_index: OpenSearchIndex,
) -> None:
    document_id = uuid.uuid4()
    chunk = _chunk(_TENANT_ID, document_id, "termination clause")
    await search_index.index_chunks([chunk])

    await search_index.mark_document_chunks_deleted(
        tenant_id=_OTHER_TENANT_ID, document_id=document_id
    )

    assert await _found_ids(search_index, _TENANT_ID) == {chunk.id}


async def test_a_vector_written_after_flagging_does_not_bring_the_chunk_back(
    search_index: OpenSearchIndex,
) -> None:
    document_id = uuid.uuid4()
    chunk = _chunk(_TENANT_ID, document_id, "termination clause")
    await search_index.index_chunks([chunk])
    await search_index.mark_document_chunks_deleted(
        tenant_id=_TENANT_ID, document_id=document_id
    )

    await search_index.set_chunk_embeddings(
        tenant_id=_TENANT_ID, embeddings={chunk.id: [0.5] * 1024}
    )

    assert await _found_ids(search_index, _TENANT_ID) == set()


async def test_updating_the_mapping_adds_the_flag_to_an_older_index_and_keeps_its_chunks(
    _opensearch_url: str,
) -> None:
    index = OpenSearchIndex(SearchSettings(search_url=_opensearch_url))
    older_body = index_body()
    del older_body["mappings"]["properties"]["deleted"]
    async with AsyncOpenSearch(hosts=[_opensearch_url]) as client:
        await client.indices.create(
            index=versioned_index_name("voyage-4-large-1024"), body=older_body
        )
        document_id = uuid.uuid4()
        chunk = _chunk(_TENANT_ID, document_id, "termination clause")
        await index.index_chunks([chunk])

        await index.update_mapping()
        await index.update_mapping()
        await index.mark_document_chunks_deleted(
            tenant_id=_TENANT_ID, document_id=document_id
        )

        mapping = (await client.indices.get_mapping(index="kith-chunks")).popitem()[1]
        assert mapping["mappings"]["properties"]["deleted"]["type"] == "boolean"
        assert await _found_ids(index, _TENANT_ID) == set()
        stored = await client.get(index="kith-chunks", id=str(chunk.id))
        assert stored["_source"]["text"] == "termination clause"
        await client.indices.delete(index="kith-chunks-*", ignore=[404])
    await index.close()
