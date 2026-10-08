"""HTTP tests for Search by meaning (#83): the keyword and meaning legs merged
by reciprocal rank fusion, through the real app, Postgres and OpenSearch, and
the fallback to keyword alone (ADR-0015)."""

import uuid

import pytest
from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.circuit_breaker_provider import CircuitBreakerEmbeddingProvider
from core.embedding.exceptions import EmbeddingUnavailableError
from core.embedding.provider import EmbeddingInputType
from core.search.opensearch_index import OpenSearchIndex
from documents.dependencies import get_query_embedding_provider
from documents.models import Document
from httpx import AsyncClient
from main import app
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents.conftest import Caller, make_tenant
from tests.documents.test_search import _index_chunk, _search, _seed_document
from tests.support.fake_embedding_provider import FakeEmbeddingProvider, axis_vector

QUERY = "payment terms"


@pytest.fixture(autouse=True)
def _search_endpoint(search_endpoint: None) -> None:
    """Every test here searches the real OpenSearch container."""


async def _embedded_chunk(
    search_index: OpenSearchIndex,
    document: Document,
    text: str,
    vector: list[float],
    *,
    ordinal: int = 0,
) -> uuid.UUID:
    chunk = await _index_chunk(search_index, document, text, ordinal=ordinal)
    await search_index.set_chunk_embeddings(
        tenant_id=document.tenant_id, embeddings={chunk.id: vector}
    )
    return chunk.id


def _ids(response) -> list[str]:
    return [result["chunk_id"] for result in response.json()["results"]]


async def test_a_passage_with_the_queries_meaning_but_none_of_its_words_is_found(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
) -> None:
    fake_embedding_provider.vectors[QUERY] = axis_vector(0)
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    chunk_id = await _embedded_chunk(
        search_index, document, "Invoices are due within 30 days.", axis_vector(0)
    )

    response = await _search(client, QUERY)

    assert response.status_code == 200
    assert response.json()["degraded"] is False
    [result] = response.json()["results"]
    assert result["chunk_id"] == str(chunk_id)
    assert result["highlights"] == []
    assert fake_embedding_provider.requests == [[QUERY]]
    assert fake_embedding_provider.input_types == [EmbeddingInputType.QUERY]


async def test_a_passage_with_the_queries_words_but_another_meaning_is_found(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
) -> None:
    fake_embedding_provider.vectors[QUERY] = axis_vector(0)
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    chunk_id = await _embedded_chunk(
        search_index, document, "The payment terms are listed.", axis_vector(5)
    )

    response = await _search(client, QUERY)

    [result] = response.json()["results"]
    assert result["chunk_id"] == str(chunk_id)
    assert result["highlights"] == ["The <mark>payment</mark> <mark>terms</mark> are listed."]


async def test_a_passage_found_by_both_ranks_above_one_found_by_either(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
) -> None:
    fake_embedding_provider.vectors[QUERY] = axis_vector(0)
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    # The nearest in meaning, with none of the words.
    meaning_only = await _embedded_chunk(
        search_index, document, "Invoices are due within 30 days.", axis_vector(0)
    )
    # Not the nearest in meaning, but it has the words too.
    both = await _embedded_chunk(
        search_index,
        document,
        "The payment terms are net 30.",
        [1.0, 0.5] + [0.0] * 1022,
        ordinal=1,
    )
    keyword_only = (
        await _index_chunk(
            search_index, document, "Payment is made by transfer.", ordinal=2
        )
    ).id

    response = await _search(client, QUERY)

    assert _ids(response) == [str(both), str(meaning_only), str(keyword_only)]


async def test_a_chunk_without_a_vector_is_found_by_keyword_among_embedded_ones(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
) -> None:
    fake_embedding_provider.vectors[QUERY] = axis_vector(0)
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _embedded_chunk(
        search_index, document, "Unrelated, embedded.", axis_vector(7)
    )
    unembedded = await _index_chunk(
        search_index, document, "The payment terms.", ordinal=1
    )

    response = await _search(client, QUERY)

    assert str(unembedded.id) in _ids(response)


async def test_another_tenants_chunks_never_use_up_the_meaning_leg(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
) -> None:
    """The Tenant filter is inside the kNN clause: other Tenants' Chunks that
    sit closer to the Query must not crowd the caller's out of the top k."""
    fake_embedding_provider.vectors[QUERY] = axis_vector(0)
    other_document = await _seed_document(
        db_session, tenant_id=await make_tenant(db_session)
    )
    for ordinal in range(40):
        await _embedded_chunk(
            search_index,
            other_document,
            f"Other tenant {ordinal}.",
            axis_vector(0),
            ordinal=ordinal,
        )
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    own = await _embedded_chunk(
        search_index, document, "Our own passage.", [1.0, 5.0] + [0.0] * 1022
    )

    response = await _search(client, QUERY)

    assert _ids(response) == [str(own)]


async def test_a_flagged_deleted_chunk_is_not_found_by_meaning(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _embedded_chunk(search_index, document, "Gone.", axis_vector(0))
    await search_index.mark_document_chunks_deleted(
        tenant_id=caller.tenant_id, document_id=document.id
    )

    hits = await search_index.search_chunks(
        tenant_id=caller.tenant_id,
        query=QUERY,
        query_vector=axis_vector(0),
        size=10,
    )

    assert hits == []


async def test_search_answers_by_keyword_alone_when_the_embedding_model_is_down(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
) -> None:
    fake_embedding_provider.is_down = True
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    chunk = await _index_chunk(search_index, document, "The payment terms.")

    response = await _search(client, QUERY)

    assert response.status_code == 200
    assert response.json()["degraded"] is True
    assert _ids(response) == [str(chunk.id)]


async def test_search_answers_by_keyword_alone_when_the_embedding_breaker_is_open(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
) -> None:
    fake_embedding_provider.is_down = True
    breaker = CircuitBreaker(
        name="embedding",
        failure_threshold=1,
        reset_timeout_seconds=60,
        failure_types=(EmbeddingUnavailableError,),
    )
    guarded = CircuitBreakerEmbeddingProvider(fake_embedding_provider, breaker)
    app.dependency_overrides[get_query_embedding_provider] = lambda: guarded
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    chunk = await _index_chunk(search_index, document, "The payment terms.")

    await _search(client, QUERY)
    calls_before = fake_embedding_provider.embed_calls
    response = await _search(client, QUERY)

    assert fake_embedding_provider.embed_calls == calls_before
    assert response.json()["degraded"] is True
    assert _ids(response) == [str(chunk.id)]


async def test_search_runs_keyword_only_when_there_is_no_voyage_key(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
) -> None:
    app.dependency_overrides[get_query_embedding_provider] = lambda: None
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    chunk = await _index_chunk(search_index, document, "The payment terms.")

    response = await _search(client, QUERY)

    assert response.status_code == 200
    assert response.json()["degraded"] is True
    assert _ids(response) == [str(chunk.id)]
