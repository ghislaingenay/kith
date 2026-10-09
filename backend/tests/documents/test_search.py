"""HTTP tests for Search (#80): Retrieval's keyword leg over the caller's
Tenant, through the real app, Postgres and OpenSearch."""

import logging
import uuid
from datetime import UTC, datetime

import pytest
import structlog
from arq.connections import RedisSettings
from core.circuit_breaker.breaker import CircuitBreaker
from core.logging.config import LoggingSettings, configure_logging
from core.ratelimit.dependencies import get_rate_limiter
from core.ratelimit.limiter import SlidingWindowLimiter
from core.search.circuit_breaker_index import CircuitBreakerSearchIndex
from core.search.dependencies import get_search_index
from core.search.exceptions import SearchUnavailableError
from core.search.provider import ChunkDocument, SearchIndex
from documents.models import Document, IngestionStage, IngestionStatus
from httpx import AsyncClient
from main import app
from redis import asyncio as redis_asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from tenants.permissions import Role

from tests.documents.conftest import Caller, make_tenant
from tests.support.fake_reranker import FakeReranker
from tests.support.fake_search_index import FakeSearchIndex

SEARCH_URL = "/api/v1/search"
_DELETED_AT = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _search_endpoint(search_endpoint: None) -> None:
    """Every test here searches the real OpenSearch container."""


async def _seed_document(
    db_session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str = "report.pdf",
    status: IngestionStatus = IngestionStatus.READY,
    stage: IngestionStage | None = None,
) -> Document:
    document = Document(
        tenant_id=tenant_id,
        name=name,
        size_bytes=1024,
        page_count=3,
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_key="tenants/x/documents/y.pdf",
        ingestion_status=status,
        ingestion_stage=stage,
        deleted_at=_DELETED_AT if status == IngestionStatus.DELETED else None,
    )
    db_session.add(document)
    await db_session.commit()
    return document


async def _index_chunk(
    search_index: SearchIndex,
    document: Document,
    text: str,
    *,
    page_number: int = 1,
    ordinal: int = 0,
) -> ChunkDocument:
    chunk = ChunkDocument(
        id=uuid.uuid4(),
        tenant_id=document.tenant_id,
        document_id=document.id,
        page_number=page_number,
        ordinal=ordinal,
        text=text,
    )
    await search_index.index_chunks([chunk])
    return chunk


async def _search(client: AsyncClient, query: str):
    return await client.post(SEARCH_URL, json={"query": query})


async def test_a_query_returns_the_matching_chunk_with_its_document_and_highlights(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
) -> None:
    document = await _seed_document(
        db_session, tenant_id=caller.tenant_id, name="contract.pdf"
    )
    chunk = await _index_chunk(
        search_index,
        document,
        "The termination clause ends the contract.",
        page_number=4,
    )
    await _index_chunk(search_index, document, "Nothing relevant here.", ordinal=1)

    response = await _search(client, "termination")

    assert response.status_code == 200
    assert response.json() == {
        "degraded": False,
        "results": [
            {
                "chunk_id": str(chunk.id),
                "document_id": str(document.id),
                "document_name": "contract.pdf",
                "document_status": "ready",
                "page_number": 4,
                "text": "The termination clause ends the contract.",
                "highlights": [
                    "The <mark>termination</mark> clause ends the contract."
                ],
            }
        ],
    }


async def test_a_chunk_from_another_tenant_is_never_returned(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
) -> None:
    other_tenant_id = await make_tenant(db_session)
    other_document = await _seed_document(db_session, tenant_id=other_tenant_id)
    await _index_chunk(search_index, other_document, "The termination clause.")
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    own_chunk = await _index_chunk(search_index, document, "Termination in writing.")

    response = await _search(client, "termination")

    assert [result["chunk_id"] for result in response.json()["results"]] == [
        str(own_chunk.id)
    ]


async def test_a_deleted_documents_chunks_are_not_returned_while_still_indexed(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
) -> None:
    deleted = await _seed_document(
        db_session, tenant_id=caller.tenant_id, status=IngestionStatus.DELETED
    )
    await _index_chunk(search_index, deleted, "The termination clause.")
    live = await _seed_document(db_session, tenant_id=caller.tenant_id)
    live_chunk = await _index_chunk(search_index, live, "Termination in writing.")

    response = await _search(client, "termination")

    assert [result["chunk_id"] for result in response.json()["results"]] == [
        str(live_chunk.id)
    ]


async def test_a_document_deleted_through_the_api_is_no_longer_searched(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    document.uploader_id = caller.user_id
    await db_session.commit()
    await _index_chunk(search_index, document, "The termination clause.")

    assert (await client.delete(f"/api/v1/documents/{document.id}")).status_code == 204

    response = await _search(client, "termination")
    assert response.json()["results"] == []
    assert (
        await search_index.search_chunks(
            tenant_id=caller.tenant_id, query="termination", size=10
        )
        == []
    )


async def test_deleted_documents_do_not_use_up_the_results(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
) -> None:
    deleted = await _seed_document(
        db_session, tenant_id=caller.tenant_id, status=IngestionStatus.DELETED
    )
    live = await _seed_document(db_session, tenant_id=caller.tenant_id)
    for ordinal in range(10):
        await _index_chunk(search_index, deleted, "termination", ordinal=ordinal)
    for ordinal in range(25):
        await _index_chunk(search_index, live, "termination", ordinal=ordinal)

    response = await _search(client, "termination")

    results = response.json()["results"]
    assert len(results) == 20
    assert {result["document_id"] for result in results} == {str(live.id)}


async def test_a_chunk_of_a_document_still_at_the_embedding_stage_is_returned(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
) -> None:
    document = await _seed_document(
        db_session,
        tenant_id=caller.tenant_id,
        status=IngestionStatus.PROCESSING,
        stage=IngestionStage.EMBEDDING,
    )
    await _index_chunk(search_index, document, "The termination clause.")

    response = await _search(client, "termination")

    [result] = response.json()["results"]
    assert result["document_status"] == "processing"


async def test_most_of_the_words_must_match_and_the_exact_phrase_ranks_first(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    scattered = await _index_chunk(
        search_index,
        document,
        "Months after the twelve week notice, the contract ends.",
    )
    phrase = await _index_chunk(
        search_index, document, "The contract ends twelve months later.", ordinal=1
    )
    await _index_chunk(search_index, document, "The contract was signed.", ordinal=2)

    response = await _search(client, "contract ends twelve months")

    assert [result["chunk_id"] for result in response.json()["results"]] == [
        str(phrase.id),
        str(scattered.id),
    ]


async def test_the_query_is_cleaned_like_the_chunks_were(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_chunk(search_index, document, "The final contract.")

    ligature = await _search(client, "  \ufb01nal  ")
    soft_hyphen = await _search(client, "con\u00adtract")

    assert len(ligature.json()["results"]) == 1
    assert len(soft_hyphen.json()["results"]) == 1


@pytest.mark.parametrize("query", ["", "   ", "\u200b\u00ad"])
async def test_a_query_that_is_blank_after_cleaning_is_rejected(
    client: AsyncClient, query: str
) -> None:
    response = await _search(client, query)

    assert response.status_code == 422


async def test_highlights_escape_the_chunks_own_markup(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_chunk(search_index, document, "Use <script>termination</script> here.")

    response = await _search(client, "termination")

    [result] = response.json()["results"]
    assert result["highlights"] == [
        "Use &lt;script&gt;<mark>termination</mark>&lt;&#x2F;script&gt; here."
    ]


@pytest.mark.parametrize("role", list(Role))
async def test_every_role_may_search(
    client: AsyncClient, caller: Caller, role: Role
) -> None:
    caller.role = role

    response = await _search(client, "termination")

    assert response.status_code == 200


async def test_a_search_store_that_is_down_answers_503(
    client: AsyncClient,
) -> None:
    index = FakeSearchIndex()
    index.search_down = True
    app.dependency_overrides[get_search_index] = lambda: index

    response = await _search(client, "termination")

    assert response.status_code == 503
    assert response.json()["error"] == "search_unavailable"


async def test_an_open_circuit_breaker_answers_503(client: AsyncClient) -> None:
    down_index = FakeSearchIndex()
    down_index.search_down = True
    breaker = CircuitBreaker(
        name="search",
        failure_threshold=1,
        reset_timeout_seconds=60,
        failure_types=(SearchUnavailableError,),
    )
    index = CircuitBreakerSearchIndex(down_index, breaker)  # type: ignore[arg-type]
    app.dependency_overrides[get_search_index] = lambda: index

    await _search(client, "termination")
    response = await _search(client, "termination")

    assert response.status_code == 503
    assert response.json()["error"] == "search_unavailable"


async def test_a_user_is_limited_to_60_searches_a_minute(
    client: AsyncClient, _redis_settings: RedisSettings
) -> None:
    redis_client = redis_asyncio.Redis(
        host=_redis_settings.host,
        port=_redis_settings.port,
        decode_responses=True,
    )
    await redis_client.flushall()
    app.dependency_overrides[get_rate_limiter] = lambda: SlidingWindowLimiter(
        redis_client
    )

    statuses = [(await _search(client, "termination")).status_code for _ in range(61)]
    await redis_client.aclose()

    assert statuses == [200] * 60 + [429]


async def test_search_never_calls_the_reranker(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_chunk(search_index, document, "The termination clause.")

    response = await _search(client, "termination")

    assert len(response.json()["results"]) == 1
    assert fake_reranker.requests == []


async def test_the_query_text_is_never_logged(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    search_index: SearchIndex,
    caplog: pytest.LogCaptureFixture,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_chunk(search_index, document, "A confidential merger plan.")
    configure_logging(LoggingSettings())
    caplog.set_level(logging.INFO)

    with structlog.testing.capture_logs() as structured_logs:
        await _search(client, "confidential merger")

    assert "confidential" not in repr(structured_logs) + caplog.text
    assert {
        "logger_name": "documents.retrieval_service",
        "event": "search_completed",
        "tenant_id": str(caller.tenant_id),
        "user_id": str(caller.user_id),
        "result_count": 1,
        "degraded": False,
        "log_level": "info",
    } in structured_logs
