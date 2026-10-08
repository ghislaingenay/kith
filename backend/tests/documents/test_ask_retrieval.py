"""Ask's Retrieval (#93): 50 candidates from hybrid Retrieval, less deleted
Documents, reranked down to 5, against the real Postgres and OpenSearch, with
the fake embedding provider and the fake reranker (ADR-0015)."""

import pytest
import structlog
from core.logging.config import LoggingSettings, configure_logging
from core.rerank.config import RerankSettings
from core.search.opensearch_index import OpenSearchIndex
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

QUERY = "payment terms"


def _service(
    db_session: AsyncSession,
    search_index: OpenSearchIndex,
    embedding_provider: FakeEmbeddingProvider | None,
    reranker: FakeReranker | None,
    *,
    fetch_size: int = 50,
    result_limit: int = 5,
) -> RetrievalService:
    return RetrievalService(
        DocumentsRepository(db_session),
        search_index,
        embedding_provider,
        RetrievalSettings(),
        reranker,
        RerankSettings(fetch_size=fetch_size, result_limit=result_limit),
    )


async def _index_payment_chunks(
    search_index: OpenSearchIndex, document: Document, count: int
) -> list[str]:
    texts = [f"Payment terms, clause {ordinal}." for ordinal in range(count)]
    for ordinal, text in enumerate(texts):
        await _index_chunk(search_index, document, text, ordinal=ordinal)
    return texts


async def _retrieve(
    service: RetrievalService, caller: Caller, query: str = QUERY
) -> AskRetrieval:
    return await service.retrieve_for_ask(
        tenant_id=caller.tenant_id, user_id=caller.user_id, query=query
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
