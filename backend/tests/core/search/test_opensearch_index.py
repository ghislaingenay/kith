"""Against a real OpenSearch container: the index mapping and the keyword
analysis chain of ADR-0012 and ADR-0011."""

from collections.abc import AsyncIterator

import pytest
from core.search.config import SearchSettings
from core.search.opensearch_index import OpenSearchIndex
from opensearchpy import AsyncOpenSearch

_ALIAS = "kith-chunks"
_VERSIONED_INDEX = "kith-chunks-voyage-4-large-1024-v1"
_VECTOR_DIMENSION = 1024


@pytest.fixture
async def client(_opensearch_url: str) -> AsyncIterator[AsyncOpenSearch]:
    async with AsyncOpenSearch(hosts=[_opensearch_url]) as opensearch_client:
        yield opensearch_client
        await opensearch_client.indices.delete(index="kith-chunks-*", ignore=[404])


@pytest.fixture
def search_index(_opensearch_url: str) -> OpenSearchIndex:
    return OpenSearchIndex(
        SearchSettings(
            search_url=_opensearch_url, embedding_model_id="Voyage-4-Large-1024"
        )
    )


async def _search_text(client: AsyncOpenSearch, query: str) -> int:
    response = await client.search(
        index=_ALIAS, body={"query": {"match": {"text": query}}}
    )
    return response["hits"]["total"]["value"]


async def _index_text(client: AsyncOpenSearch, text: str) -> None:
    await client.index(
        index=_ALIAS,
        body={"text": text, "tenant_id": "t", "document_id": "d", "page_number": 1},
        refresh=True,
    )


async def test_alias_is_missing_before_ensure_index(
    search_index: OpenSearchIndex,
) -> None:
    assert await search_index.alias_exists() is False


async def test_ensure_index_creates_the_versioned_index_behind_the_alias(
    search_index: OpenSearchIndex, client: AsyncOpenSearch
) -> None:
    await search_index.ensure_index()

    assert await search_index.alias_exists() is True
    mapping = (await client.indices.get_mapping(index=_ALIAS))[_VERSIONED_INDEX][
        "mappings"
    ]
    assert mapping["dynamic"] == "strict"
    assert mapping["_meta"] == {"mapping_version": 1}
    assert mapping["properties"]["embedding"]["dimension"] == _VECTOR_DIMENSION
    assert mapping["properties"]["embedding"]["method"]["name"] == "hnsw"
    assert mapping["properties"]["embedding"]["method"]["engine"] == "faiss"
    assert mapping["properties"]["embedding"]["space_type"] == "cosinesimil"


async def test_ensure_index_twice_changes_nothing(
    search_index: OpenSearchIndex, client: AsyncOpenSearch
) -> None:
    await search_index.ensure_index()
    before = await client.indices.get(index=_ALIAS)

    await search_index.ensure_index()

    assert await client.indices.get(index=_ALIAS) == before
    assert list(await client.indices.get(index="kith-chunks-*")) == [_VERSIONED_INDEX]


async def test_a_word_with_an_accent_is_found_without_it(
    search_index: OpenSearchIndex, client: AsyncOpenSearch
) -> None:
    await search_index.ensure_index()
    await _index_text(client, "Please send your résumé")

    assert await _search_text(client, "resume") == 1


async def test_a_different_case_finds_the_match(
    search_index: OpenSearchIndex, client: AsyncOpenSearch
) -> None:
    await search_index.ensure_index()
    await _index_text(client, "The Contract was signed")

    assert await _search_text(client, "CONTRACT") == 1


async def test_a_straight_apostrophe_finds_a_curly_one(
    search_index: OpenSearchIndex, client: AsyncOpenSearch
) -> None:
    await search_index.ensure_index()
    await _index_text(client, "the client’s contract")

    assert await _search_text(client, "client's") == 1


async def test_spanish_text_is_searchable_through_the_same_chain(
    search_index: OpenSearchIndex, client: AsyncOpenSearch
) -> None:
    await search_index.ensure_index()
    await _index_text(client, "Información sobre el niño")

    assert await _search_text(client, "informacion") == 1
    assert await _search_text(client, "NINO") == 1
