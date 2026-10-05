"""Tests for #67: embedding degrades in a defined way when the embedding model
is unavailable or rejects a batch (ADR-0014). Same seam as the other
embedding tests (`embed_document` called directly, real Postgres, a
`FakeSearchIndex`), with a scripted `FakeEmbeddingProvider` and, where the
breaker matters, the real breaker around it on a fake clock."""

import uuid
from collections.abc import AsyncIterator

import pytest
from core.circuit_breaker.breaker import CircuitBreaker
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.embedding.circuit_breaker_provider import CircuitBreakerEmbeddingProvider
from core.embedding.exceptions import EmbeddingUnavailableError
from documents.config import IngestionSettings
from documents.embed import embed_document
from documents.models import (
    ChunkDeadLetter,
    ChunkDeadLetterStatus,
    ChunkStatus,
    IngestionStage,
    IngestionStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents.conftest import Caller, fast_retry_handler
from tests.documents.embedding_support import (
    document_waiting_at_embedding,
    load_chunks,
    load_document,
)
from tests.support.fake_embedding_provider import FakeEmbeddingProvider
from tests.support.fake_search_index import FakeSearchIndex

_BREAKER_FAILURE_THRESHOLD = 5
_TEXTS = ["first chunk", "second chunk", "third chunk"]


@pytest.fixture
def search_index() -> FakeSearchIndex:
    return FakeSearchIndex()


@pytest.fixture
def embedding_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture
def breaker() -> CircuitBreaker:
    return CircuitBreaker(
        name="embedding",
        failure_threshold=_BREAKER_FAILURE_THRESHOLD,
        reset_timeout_seconds=30,
        failure_types=(EmbeddingUnavailableError,),
        clock=lambda: 0.0,
    )


@pytest.fixture
async def embed_ctx(
    _database_url: str,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    breaker: CircuitBreaker,
) -> AsyncIterator[dict]:
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield {
        "db_session_factory": create_session_factory(engine),
        # One Chunk per request.
        "ingestion_settings": IngestionSettings.model_validate(
            {"INGESTION_EMBED_BATCH_MAX_CHUNKS": 1}
        ),
        "search_index": search_index,
        "embedding_provider": CircuitBreakerEmbeddingProvider(
            embedding_provider, breaker
        ),
        "retry_handler": fast_retry_handler(),
    }
    await engine.dispose()


async def _embed(ctx: dict, caller: Caller, document_id: uuid.UUID) -> None:
    await embed_document(
        ctx, document_id=str(document_id), tenant_id=str(caller.tenant_id)
    )


async def _dead_letters(
    db_session: AsyncSession, document_id: uuid.UUID
) -> list[ChunkDeadLetter]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                select(ChunkDeadLetter)
                .where(ChunkDeadLetter.document_id == document_id)
                .order_by(ChunkDeadLetter.created_at, ChunkDeadLetter.attempts.desc())
            )
        ).scalars()
    )


async def test_a_provider_that_fails_twice_then_succeeds_embeds_every_chunk(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["only chunk"]
    )
    embedding_provider.embed_outcomes = [False, False, True]

    await _embed(embed_ctx, caller, document_id)

    (chunk,) = await load_chunks(db_session, document_id)
    assert chunk.embedding_status == ChunkStatus.DONE
    assert embedding_provider.embed_calls == 3
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.READY
    )
    assert await _dead_letters(db_session, document_id) == []


async def test_a_batch_that_fails_after_the_retries_is_recorded_and_the_others_are_embedded(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, _TEXTS
    )
    # Chunk 1 works, chunk 2 fails all three attempts, chunk 3 works.
    embedding_provider.embed_outcomes = [True, False, False, False, True]

    await _embed(embed_ctx, caller, document_id)

    first, second, third = await load_chunks(db_session, document_id)
    assert [first.embedding_status, third.embedding_status] == [ChunkStatus.DONE] * 2
    assert second.embedding_status == ChunkStatus.FAILED
    assert second.embedding_error
    assert set(search_index.embeddings) == {first.id, third.id}
    chunk_error = second.embedding_error
    second_id = second.id
    (dead_letter,) = await _dead_letters(db_session, document_id)
    assert dead_letter.tenant_id == caller.tenant_id
    assert dead_letter.document_id == document_id
    assert dead_letter.stage == IngestionStage.EMBEDDING
    assert dead_letter.chunk_ids == [second_id]
    assert dead_letter.error == chunk_error
    assert dead_letter.attempts == 3
    assert dead_letter.status == ChunkDeadLetterStatus.OPEN
    document = await load_document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PARTIAL
    assert document.ingestion_error


async def test_a_document_whose_every_batch_fails_is_failed(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, _TEXTS[:2]
    )
    embedding_provider.is_down = True

    await _embed(embed_ctx, caller, document_id)

    chunks = await load_chunks(db_session, document_id)
    assert [chunk.embedding_status for chunk in chunks] == [ChunkStatus.FAILED] * 2
    assert len(await _dead_letters(db_session, document_id)) == 2
    document = await load_document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.FAILED
    assert document.ingestion_error


async def test_a_rejected_batch_is_recorded_at_once_and_does_not_open_the_breaker(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    # More rejected batches than the breaker's threshold of five, then one
    # that works: it still reaches the provider.
    texts = [f"rejected chunk {n}" for n in range(6)] + ["good chunk"]
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, texts
    )
    embedding_provider.rejected_texts = set(texts[:6])

    await _embed(embed_ctx, caller, document_id)

    *rejected, good = await load_chunks(db_session, document_id)
    assert [chunk.embedding_status for chunk in rejected] == [ChunkStatus.FAILED] * 6
    assert good.embedding_status == ChunkStatus.DONE
    dead_letters = await _dead_letters(db_session, document_id)
    assert [dead_letter.attempts for dead_letter in dead_letters] == [1] * 6
    assert embedding_provider.embed_calls == 7
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PARTIAL
    )


async def test_five_consecutive_unavailable_failures_open_the_breaker_and_later_calls_fail_fast(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, _TEXTS
    )
    embedding_provider.is_down = True

    await _embed(embed_ctx, caller, document_id)

    # Chunk 1 uses three calls, chunk 2 two more and then the open breaker;
    # chunk 3 is turned away without a call.
    assert embedding_provider.embed_calls == 5
    first, second, third = await _dead_letters(db_session, document_id)
    assert (first.attempts, second.attempts, third.attempts) == (3, 2, 0)
    assert "embedding" in third.error
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )


async def test_a_chunk_that_failed_embedding_is_not_searchable_so_the_document_is_partial(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, _TEXTS
    )
    document = await load_document(db_session, document_id)
    first, second, _ = await load_chunks(db_session, document_id)
    first.indexing_status = ChunkStatus.FAILED
    second.embedding_status = ChunkStatus.FAILED
    document.ingestion_status = IngestionStatus.PARTIAL
    await db_session.commit()

    await _embed(embed_ctx, caller, document_id)

    document = await load_document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PARTIAL
    assert embedding_provider.requests == [["third chunk"]]


async def test_a_failure_outside_the_embedding_model_raises_and_leaves_the_chunks_pending(
    caller: Caller,
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    embed_ctx: dict,
) -> None:
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["only chunk"]
    )
    embedding_provider.crash_with = RuntimeError("database went away")

    with pytest.raises(RuntimeError):
        await _embed(embed_ctx, caller, document_id)

    (chunk,) = await load_chunks(db_session, document_id)
    assert chunk.embedding_status == ChunkStatus.PENDING
    assert await _dead_letters(db_session, document_id) == []
