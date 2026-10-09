"""Ask's Retrieval (#93): 50 candidates from hybrid Retrieval, less deleted
Documents, reranked down to 5, against the real Postgres and OpenSearch, with
the fake embedding provider and the fake reranker (ADR-0015)."""

import asyncio

import pytest
import structlog
from core.circuit_breaker.breaker import CircuitBreaker
from core.circuit_breaker.exceptions import CircuitOpenError
from core.logging.config import LoggingSettings, configure_logging
from core.rerank.circuit_breaker_reranker import CircuitBreakerReranker
from core.rerank.config import RerankSettings
from core.rerank.exceptions import RerankUnavailableError
from core.rerank.provider import Reranker
from core.rerank.time_limited_reranker import TimeLimitedReranker
from core.search.circuit_breaker_index import CircuitBreakerSearchIndex
from core.search.exceptions import SearchUnavailableError
from core.search.opensearch_index import OpenSearchIndex
from core.search.provider import SearchIndex
from documents.config import RetrievalSettings
from documents.exceptions import BlankQueryError
from documents.models import Document, IngestionStatus
from documents.repository import DocumentsRepository
from documents.retrieval_service import AskRetrieval, RetrievalService
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents.conftest import Caller, make_tenant
from tests.documents.test_search import _index_chunk, _seed_document
from tests.support.fake_embedding_provider import FakeEmbeddingProvider
from tests.support.fake_reranker import FakeReranker
from tests.support.fake_search_index import FakeSearchIndex

QUERY = "payment terms"


def _service(
    db_session: AsyncSession,
    search_index: SearchIndex,
    embedding_provider: FakeEmbeddingProvider | None,
    reranker: Reranker | None,
    *,
    fetch_size: int = 50,
    result_limit: int = 5,
    enabled: bool = True,
) -> RetrievalService:
    return RetrievalService(
        DocumentsRepository(db_session),
        search_index,
        embedding_provider,
        RetrievalSettings(),
        reranker,
        RerankSettings(
            enabled=enabled, fetch_size=fetch_size, result_limit=result_limit
        ),
    )


async def _index_payment_chunks(
    search_index: OpenSearchIndex, document: Document, count: int
) -> list[str]:
    texts = [f"Payment terms, clause {ordinal}." for ordinal in range(count)]
    for ordinal, text in enumerate(texts):
        await _index_chunk(search_index, document, text, ordinal=ordinal)
    return texts


async def _retrieve(
    service: RetrievalService,
    caller: Caller,
    query: str = QUERY,
    *,
    rerank: bool | None = None,
) -> AskRetrieval:
    return await service.retrieve_for_ask(
        tenant_id=caller.tenant_id, user_id=caller.user_id, query=query, rerank=rerank
    )


async def test_the_rerankers_best_chunks_are_kept_in_its_order_with_their_scores(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    texts = await _index_payment_chunks(search_index, document, 8)
    fake_reranker.scores = {texts[3]: 0.9, texts[6]: 0.7, texts[0]: 0.5}

    retrieval = await _retrieve(
        _service(
            db_session,
            search_index,
            fake_embedding_provider,
            fake_reranker,
            result_limit=2,
        ),
        caller,
    )

    assert retrieval.is_reranked is True
    assert retrieval.degraded is False
    assert [(chunk.result.text, chunk.rerank_score) for chunk in retrieval.chunks] == [
        (texts[3], 0.9),
        (texts[6], 0.7),
    ]
    assert retrieval.chunks[0].result.document_name == "report.pdf"
    [(query, _)] = fake_reranker.requests
    assert query == QUERY


async def test_a_chunk_retrieval_ranked_below_the_limit_can_be_returned_first(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_payment_chunks(search_index, document, 6)
    service = _service(
        db_session, search_index, fake_embedding_provider, fake_reranker, result_limit=2
    )
    unreranked = await _retrieve(
        _service(
            db_session, search_index, fake_embedding_provider, None, result_limit=6
        ),
        caller,
    )
    last_in_retrievals_order = unreranked.chunks[-1].result.text
    fake_reranker.scores = {last_in_retrievals_order: 0.99}

    retrieval = await _retrieve(service, caller)

    assert retrieval.chunks[0].result.text == last_in_retrievals_order


async def test_the_reranker_gets_at_most_the_fetch_size_and_never_a_deleted_document(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    deleted = await _seed_document(
        db_session, tenant_id=caller.tenant_id, status=IngestionStatus.DELETED
    )
    await _index_chunk(search_index, deleted, "Payment terms of a deleted file.")
    live = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_payment_chunks(search_index, live, 6)

    await _retrieve(
        _service(
            db_session,
            search_index,
            fake_embedding_provider,
            fake_reranker,
            fetch_size=4,
            result_limit=2,
        ),
        caller,
    )

    [(_, texts)] = fake_reranker.requests
    assert 0 < len(texts) <= 4
    assert "Payment terms of a deleted file." not in texts


async def test_only_the_callers_tenants_chunks_are_returned(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    other = await _seed_document(db_session, tenant_id=await make_tenant(db_session))
    await _index_chunk(search_index, other, "Payment terms of another tenant.")
    own = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_chunk(search_index, own, "Our payment terms.")

    retrieval = await _retrieve(
        _service(db_session, search_index, fake_embedding_provider, fake_reranker),
        caller,
    )

    assert [chunk.result.text for chunk in retrieval.chunks] == ["Our payment terms."]
    assert fake_reranker.requests[0][1] == ["Our payment terms."]


async def test_without_a_reranker_the_top_chunks_keep_retrievals_order_unscored(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_payment_chunks(search_index, document, 6)
    search_response = await _service(
        db_session, search_index, fake_embedding_provider, None
    ).search(tenant_id=caller.tenant_id, user_id=caller.user_id, query=QUERY)

    retrieval = await _retrieve(
        _service(
            db_session, search_index, fake_embedding_provider, None, result_limit=3
        ),
        caller,
    )

    assert retrieval.is_reranked is False
    assert retrieval.degraded is False
    assert [chunk.result for chunk in retrieval.chunks] == search_response.results[:3]
    assert [chunk.rerank_score for chunk in retrieval.chunks] == [None] * 3


async def test_switched_off_rerank_keeps_retrievals_order_without_calling_the_reranker(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    texts = await _index_payment_chunks(search_index, document, 4)
    fake_reranker.scores = {texts[3]: 0.9}
    unreranked = await _retrieve(
        _service(
            db_session, search_index, fake_embedding_provider, None, result_limit=2
        ),
        caller,
    )

    retrieval = await _retrieve(
        _service(
            db_session,
            search_index,
            fake_embedding_provider,
            fake_reranker,
            result_limit=2,
            enabled=False,
        ),
        caller,
    )

    assert retrieval.is_reranked is False
    assert retrieval.chunks == unreranked.chunks
    assert fake_reranker.requests == []


async def test_forcing_rerank_on_beats_it_being_switched_off(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    texts = await _index_payment_chunks(search_index, document, 4)
    fake_reranker.scores = {texts[2]: 0.8}
    service = _service(
        db_session, search_index, fake_embedding_provider, fake_reranker, enabled=False
    )

    retrieval = await _retrieve(service, caller, rerank=True)

    assert retrieval.is_reranked is True
    assert retrieval.rerank_tokens == fake_reranker.tokens_used
    assert (retrieval.chunks[0].result.text, retrieval.chunks[0].rerank_score) == (
        texts[2],
        0.8,
    )


async def test_forcing_rerank_off_beats_it_being_switched_on(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_payment_chunks(search_index, document, 4)
    unreranked = await _retrieve(
        _service(db_session, search_index, fake_embedding_provider, None), caller
    )
    service = _service(
        db_session, search_index, fake_embedding_provider, fake_reranker, enabled=True
    )

    retrieval = await _retrieve(service, caller, rerank=False)

    assert retrieval.is_reranked is False
    assert retrieval.rerank_tokens == 0
    assert retrieval.chunks == unreranked.chunks
    assert fake_reranker.requests == []


async def test_forcing_rerank_on_without_a_reranker_falls_back(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    texts = await _index_payment_chunks(search_index, document, 3)
    service = _service(db_session, search_index, fake_embedding_provider, None)

    retrieval = await _retrieve(service, caller, rerank=True)

    assert retrieval.is_reranked is False
    assert sorted(chunk.result.text for chunk in retrieval.chunks) == texts


async def test_the_reranker_is_not_called_when_nothing_is_found(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    retrieval = await _retrieve(
        _service(db_session, search_index, fake_embedding_provider, fake_reranker),
        caller,
    )

    assert retrieval.chunks == []
    assert retrieval.is_reranked is False
    assert fake_reranker.requests == []


async def test_a_blank_query_is_rejected(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    service = _service(db_session, search_index, fake_embedding_provider, fake_reranker)

    with pytest.raises(BlankQueryError):
        await _retrieve(service, caller, query=" \u200b ")


async def test_keyword_only_retrieval_is_still_reranked_and_flagged_degraded(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    fake_embedding_provider.is_down = True
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_chunk(search_index, document, "The payment terms.")

    retrieval = await _retrieve(
        _service(db_session, search_index, fake_embedding_provider, fake_reranker),
        caller,
    )

    assert retrieval.degraded is True
    assert retrieval.is_reranked is True
    assert [chunk.result.text for chunk in retrieval.chunks] == ["The payment terms."]


async def test_one_info_line_without_the_query_and_scores_at_debug(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    text = "A confidential payment terms passage."
    await _index_chunk(search_index, document, text)
    fake_reranker.scores = {text: 0.8}
    configure_logging(LoggingSettings(level="DEBUG"))

    with structlog.testing.capture_logs() as structured_logs:
        await _retrieve(
            _service(db_session, search_index, fake_embedding_provider, fake_reranker),
            caller,
            query="confidential payment terms",
        )

    assert "confidential" not in repr(structured_logs)
    completed = [
        log for log in structured_logs if log["event"] == "ask_retrieval_completed"
    ]
    assert completed == [
        {
            "logger_name": "documents.retrieval_service",
            "event": "ask_retrieval_completed",
            "tenant_id": str(caller.tenant_id),
            "user_id": str(caller.user_id),
            "result_count": 1,
            "is_reranked": True,
            "rerank_model": "rerank-3",
            "rerank_tokens": fake_reranker.tokens_used,
            "degraded": False,
            "log_level": "info",
        }
    ]
    [scores] = [
        log for log in structured_logs if log["event"] == "ask_retrieval_rerank_scores"
    ]
    assert scores["log_level"] == "debug"
    assert scores["rerank_scores"] == [0.8]


def _rerank_breaker(failure_threshold: int = 5) -> CircuitBreaker:
    return CircuitBreaker(
        name="rerank",
        failure_threshold=failure_threshold,
        reset_timeout_seconds=30,
        failure_types=(RerankUnavailableError,),
        clock=lambda: 0.0,
    )


async def _retrievals_order(
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    caller: Caller,
    result_limit: int,
) -> list[str]:
    unreranked = await _retrieve(
        _service(
            db_session,
            search_index,
            embedding_provider,
            None,
            result_limit=result_limit,
        ),
        caller,
    )
    return [chunk.result.text for chunk in unreranked.chunks]


def _assert_fell_back(retrieval: AskRetrieval, expected_texts: list[str]) -> None:
    assert retrieval.is_reranked is False
    assert retrieval.degraded is False
    assert [chunk.result.text for chunk in retrieval.chunks] == expected_texts
    assert [chunk.rerank_score for chunk in retrieval.chunks] == [None] * len(
        expected_texts
    )


async def test_an_unavailable_reranker_keeps_retrievals_top_chunks_with_a_warning(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_payment_chunks(search_index, document, 6)
    expected = await _retrievals_order(
        db_session, search_index, fake_embedding_provider, caller, result_limit=3
    )
    fake_reranker.is_down = True

    with structlog.testing.capture_logs() as structured_logs:
        retrieval = await _retrieve(
            _service(
                db_session,
                search_index,
                fake_embedding_provider,
                fake_reranker,
                result_limit=3,
            ),
            caller,
        )

    _assert_fell_back(retrieval, expected)
    [warning] = [log for log in structured_logs if log["event"] == "rerank_failed"]
    assert warning["log_level"] == "warning"
    assert "fake reranker is down" in warning["error"]
    [completed] = [
        log for log in structured_logs if log["event"] == "ask_retrieval_completed"
    ]
    assert completed["is_reranked"] is False
    assert completed["rerank_tokens"] == 0


async def test_a_rejected_request_falls_back_and_does_not_count_toward_the_breaker(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_payment_chunks(search_index, document, 4)
    expected = await _retrievals_order(
        db_session, search_index, fake_embedding_provider, caller, result_limit=2
    )
    fake_reranker.rejects = True
    service = _service(
        db_session,
        search_index,
        fake_embedding_provider,
        CircuitBreakerReranker(fake_reranker, _rerank_breaker(failure_threshold=1)),
        result_limit=2,
    )

    first = await _retrieve(service, caller)
    fake_reranker.rejects = False
    second = await _retrieve(service, caller)

    _assert_fell_back(first, expected)
    assert second.is_reranked is True
    assert len(fake_reranker.requests) == 2


async def test_a_slow_reranker_falls_back_and_counts_toward_the_breaker(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_payment_chunks(search_index, document, 4)
    expected = await _retrievals_order(
        db_session, search_index, fake_embedding_provider, caller, result_limit=2
    )

    async def slower_than_the_time_limit() -> None:
        await asyncio.sleep(1)

    fake_reranker.after_rerank = slower_than_the_time_limit
    breaker = _rerank_breaker(failure_threshold=1)
    service = _service(
        db_session,
        search_index,
        fake_embedding_provider,
        CircuitBreakerReranker(
            TimeLimitedReranker(fake_reranker, timeout_seconds=0.01), breaker
        ),
        result_limit=2,
    )

    retrieval = await _retrieve(service, caller)

    _assert_fell_back(retrieval, expected)
    with pytest.raises(CircuitOpenError):
        await breaker.call(lambda: asyncio.sleep(0))


async def test_an_open_rerank_breaker_falls_back_without_calling_the_reranker(
    caller: Caller,
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    document = await _seed_document(db_session, tenant_id=caller.tenant_id)
    await _index_payment_chunks(search_index, document, 4)
    expected = await _retrievals_order(
        db_session, search_index, fake_embedding_provider, caller, result_limit=2
    )
    fake_reranker.is_down = True
    service = _service(
        db_session,
        search_index,
        fake_embedding_provider,
        CircuitBreakerReranker(fake_reranker, _rerank_breaker(failure_threshold=1)),
        result_limit=2,
    )
    await _retrieve(service, caller)
    fake_reranker.is_down = False

    retrieval = await _retrieve(service, caller)

    _assert_fell_back(retrieval, expected)
    assert len(fake_reranker.requests) == 1


async def test_a_search_store_outage_still_raises(
    caller: Caller,
    db_session: AsyncSession,
    fake_embedding_provider: FakeEmbeddingProvider,
    fake_reranker: FakeReranker,
) -> None:
    down_index = FakeSearchIndex()
    down_index.search_down = True
    breaker = CircuitBreaker(
        name="search",
        failure_threshold=1,
        reset_timeout_seconds=60,
        failure_types=(SearchUnavailableError,),
    )
    service = _service(
        db_session,
        CircuitBreakerSearchIndex(down_index, breaker),  # type: ignore[arg-type]
        fake_embedding_provider,
        fake_reranker,
    )

    with pytest.raises(SearchUnavailableError):
        await _retrieve(service, caller)
    with pytest.raises(SearchUnavailableError):
        await _retrieve(service, caller)
    assert fake_reranker.requests == []
