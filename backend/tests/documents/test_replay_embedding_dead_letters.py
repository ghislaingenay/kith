"""Tests for #70: replaying `embedding` Chunk Dead Letters (ADR-0014). Rows are
made by failing `embed_document` against a scripted `FakeEmbeddingProvider`;
replay is then called as a function against real Postgres and the same fakes.
Replay is given no storage, which is how the tests show it never reads the
PDF."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from documents.config import IngestionSettings
from documents.dead_letter_replay import replay_failed_batches
from documents.embed import embed_document
from documents.exceptions import EmbeddingProviderRequiredError
from documents.models import (
    Chunk,
    ChunkDeadLetter,
    ChunkDeadLetterStatus,
    ChunkStatus,
    IngestionStage,
    IngestionStatus,
)
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from structlog.testing import capture_logs

from tests.documents.conftest import Caller, fast_retry_handler
from tests.documents.embedding_support import (
    document_waiting_at_embedding,
    load_chunks,
    load_document,
)
from tests.support.fake_embedding_provider import FakeEmbeddingProvider, vector_for
from tests.support.fake_search_index import FakeSearchIndex

_TEXTS = ["first chunk", "second chunk"]
_ONE_CHUNK = ["only chunk"]


@pytest.fixture
def search_index() -> FakeSearchIndex:
    return FakeSearchIndex()


@pytest.fixture
def embedding_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


@pytest.fixture
async def session_factory(_database_url: str) -> AsyncIterator[async_sessionmaker]:
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield create_session_factory(engine)
    await engine.dispose()


async def _replay(
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider | None,
    *,
    stage: IngestionStage | None = None,
    limit: int | None = None,
) -> None:
    await replay_failed_batches(
        session_factory,
        search_index,
        embedding_provider,
        fast_retry_handler(),
        stage=stage,
        limit=limit,
    )


async def _document_with_failed_embedding(
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
    caller: Caller,
    texts: list[str] = _TEXTS,
) -> uuid.UUID:
    """A Document whose embedding failed for every Chunk, one request (and one
    open dead letter) per Chunk, then a model that works again."""
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, texts
    )
    embedding_provider.is_down = True
    await embed_document(
        {
            "db_session_factory": session_factory,
            "ingestion_settings": IngestionSettings.model_validate(
                {"INGESTION_EMBED_BATCH_MAX_CHUNKS": 1}
            ),
            "search_index": search_index,
            "embedding_provider": embedding_provider,
            "retry_handler": fast_retry_handler(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    embedding_provider.is_down = False
    embedding_provider.embed_calls = 0
    return document_id


async def _dead_letters(
    db_session: AsyncSession, document_id: uuid.UUID
) -> list[ChunkDeadLetter]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                select(ChunkDeadLetter)
                .where(ChunkDeadLetter.document_id == document_id)
                .order_by(ChunkDeadLetter.created_at, ChunkDeadLetter.id)
            )
        ).scalars()
    )


async def test_a_successful_replay_embeds_the_chunks_resolves_the_rows_and_makes_the_document_ready(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    document_id = await _document_with_failed_embedding(
        db_session, session_factory, search_index, embedding_provider, caller
    )
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )

    await _replay(session_factory, search_index, embedding_provider)

    chunks = await load_chunks(db_session, document_id)
    assert [chunk.embedding_status for chunk in chunks] == [ChunkStatus.DONE] * 2
    assert all(chunk.embedding_error is None for chunk in chunks)
    assert search_index.embeddings == {
        chunk.id: vector_for(chunk.text) for chunk in chunks
    }
    dead_letters = await _dead_letters(db_session, document_id)
    assert [d.status for d in dead_letters] == [ChunkDeadLetterStatus.RESOLVED] * 2
    assert all(d.resolved_at is not None for d in dead_letters)
    document = await load_document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.READY
    assert document.ingestion_error is None


async def test_a_replay_re_embeds_exactly_the_rows_chunks(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    document_id = await _document_with_failed_embedding(
        db_session, session_factory, search_index, embedding_provider, caller
    )

    await _replay(session_factory, search_index, embedding_provider)

    assert sorted(embedding_provider.requests) == sorted([[text] for text in _TEXTS])


async def test_a_replayed_document_with_another_failed_chunk_stays_partial(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    document_id = await _document_with_failed_embedding(
        db_session, session_factory, search_index, embedding_provider, caller
    )
    # A third Chunk the search store never took: nothing a replay of the
    # embedding rows can fix.
    db_session.add(
        Chunk(
            document_id=document_id,
            tenant_id=caller.tenant_id,
            page_number=1,
            ordinal=99,
            text="unindexed chunk",
            text_hash="unindexed",
            token_count=2,
            indexing_status=ChunkStatus.FAILED,
        )
    )
    await db_session.commit()

    await _replay(session_factory, search_index, embedding_provider)

    document = await load_document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PARTIAL
    assert document.ingestion_error


async def test_a_repeat_failure_keeps_the_row_open_with_more_attempts(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    document_id = await _document_with_failed_embedding(
        db_session,
        session_factory,
        search_index,
        embedding_provider,
        caller,
        _ONE_CHUNK,
    )
    (before,) = await _dead_letters(db_session, document_id)
    attempts_before = before.attempts
    embedding_provider.is_down = True

    await _replay(session_factory, search_index, embedding_provider)

    (after,) = await _dead_letters(db_session, document_id)
    assert after.status == ChunkDeadLetterStatus.OPEN
    assert after.resolved_at is None
    assert after.attempts > attempts_before
    assert after.error
    (chunk,) = await load_chunks(db_session, document_id)
    assert chunk.embedding_status == ChunkStatus.FAILED
    assert search_index.embeddings == {}
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )


async def test_a_repeat_failure_does_not_stop_the_other_rows(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    document_id = await _document_with_failed_embedding(
        db_session, session_factory, search_index, embedding_provider, caller
    )
    # The first row fails every attempt, the second works.
    embedding_provider.embed_outcomes = [False, False, False, True]

    await _replay(session_factory, search_index, embedding_provider)

    assert [d.status for d in await _dead_letters(db_session, document_id)] == [
        ChunkDeadLetterStatus.OPEN,
        ChunkDeadLetterStatus.RESOLVED,
    ]
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PARTIAL
    )


async def test_a_row_for_a_deleted_document_is_resolved_without_calling_the_model(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    document_id = await _document_with_failed_embedding(
        db_session, session_factory, search_index, embedding_provider, caller
    )
    document = await load_document(db_session, document_id)
    document.ingestion_status = IngestionStatus.DELETED
    document.deleted_at = datetime.now(UTC)
    await db_session.commit()

    await _replay(session_factory, search_index, embedding_provider)

    assert embedding_provider.embed_calls == 0
    assert {d.status for d in await _dead_letters(db_session, document_id)} == {
        ChunkDeadLetterStatus.RESOLVED
    }
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.DELETED
    )
    assert search_index.embeddings == {}


async def test_a_row_whose_chunks_no_longer_exist_is_resolved_without_calling_the_model(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    document_id = await _document_with_failed_embedding(
        db_session, session_factory, search_index, embedding_provider, caller
    )
    await db_session.execute(delete(Chunk).where(Chunk.document_id == document_id))
    await db_session.commit()

    await _replay(session_factory, search_index, embedding_provider)

    assert embedding_provider.embed_calls == 0
    assert {d.status for d in await _dead_letters(db_session, document_id)} == {
        ChunkDeadLetterStatus.RESOLVED
    }


async def test_a_document_deleted_during_a_replay_resolves_the_row_and_stays_deleted(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    document_id = await _document_with_failed_embedding(
        db_session,
        session_factory,
        search_index,
        embedding_provider,
        caller,
        _ONE_CHUNK,
    )

    async def delete_document_while_the_model_works() -> None:
        # What the delete and its purge leave behind: the Document marked
        # deleted and its Chunks gone from the index.
        document = await load_document(db_session, document_id)
        document.ingestion_status = IngestionStatus.DELETED
        document.deleted_at = datetime.now(UTC)
        await db_session.commit()
        search_index.indexed.clear()

    embedding_provider.after_embed = delete_document_while_the_model_works

    with capture_logs() as logs:
        await _replay(session_factory, search_index, embedding_provider)

    [warning] = [
        log for log in logs if log["event"] == "replay_embed_chunks_not_in_index"
    ]
    assert warning["log_level"] == "warning"
    assert warning["document_id"] == str(document_id)
    assert warning["chunks"] == 1
    (dead_letter,) = await _dead_letters(db_session, document_id)
    assert dead_letter.status == ChunkDeadLetterStatus.RESOLVED
    assert search_index.embeddings == {}
    (chunk,) = await load_chunks(db_session, document_id)
    assert chunk.embedding_status == ChunkStatus.FAILED
    assert (await load_document(db_session, document_id)).ingestion_status == (
        IngestionStatus.DELETED
    )


async def _document_with_failed_indexing(
    db_session: AsyncSession, search_index: FakeSearchIndex, caller: Caller
) -> uuid.UUID:
    """A Document with one Chunk that failed indexing and its open `indexing`
    dead letter, as a failed first ingestion leaves it."""
    document_id = await document_waiting_at_embedding(
        db_session, search_index, caller, ["unindexed chunk"]
    )
    (chunk,) = await load_chunks(db_session, document_id)
    chunk.indexing_status = ChunkStatus.FAILED
    search_index.indexed.clear()
    db_session.add(
        ChunkDeadLetter(
            tenant_id=caller.tenant_id,
            document_id=document_id,
            stage=IngestionStage.INDEXING,
            chunk_ids=[chunk.id],
            error="search store down",
            attempts=3,
        )
    )
    await db_session.commit()
    return document_id


async def test_without_a_stage_indexing_rows_are_replayed_before_embedding_rows(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    # The embedding row is older, so only the stage order puts the indexing
    # row first.
    embedding_document = await _document_with_failed_embedding(
        db_session,
        session_factory,
        search_index,
        embedding_provider,
        caller,
        _ONE_CHUNK,
    )
    indexing_document = await _document_with_failed_indexing(
        db_session, search_index, caller
    )

    await _replay(session_factory, search_index, embedding_provider, limit=1)

    assert {d.status for d in await _dead_letters(db_session, indexing_document)} == {
        ChunkDeadLetterStatus.RESOLVED
    }
    assert {d.status for d in await _dead_letters(db_session, embedding_document)} == {
        ChunkDeadLetterStatus.OPEN
    }


async def test_without_a_stage_both_kinds_of_rows_are_replayed(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    embedding_document = await _document_with_failed_embedding(
        db_session,
        session_factory,
        search_index,
        embedding_provider,
        caller,
        _ONE_CHUNK,
    )
    indexing_document = await _document_with_failed_indexing(
        db_session, search_index, caller
    )

    await _replay(session_factory, search_index, embedding_provider)

    assert {d.status for d in await _dead_letters(db_session, indexing_document)} == {
        ChunkDeadLetterStatus.RESOLVED
    }
    assert {d.status for d in await _dead_letters(db_session, embedding_document)} == {
        ChunkDeadLetterStatus.RESOLVED
    }


async def test_the_embedding_stage_replays_only_embedding_rows(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    embedding_document = await _document_with_failed_embedding(
        db_session,
        session_factory,
        search_index,
        embedding_provider,
        caller,
        _ONE_CHUNK,
    )
    indexing_document = await _document_with_failed_indexing(
        db_session, search_index, caller
    )

    await _replay(
        session_factory,
        search_index,
        embedding_provider,
        stage=IngestionStage.EMBEDDING,
    )

    assert {d.status for d in await _dead_letters(db_session, indexing_document)} == {
        ChunkDeadLetterStatus.OPEN
    }
    assert {d.status for d in await _dead_letters(db_session, embedding_document)} == {
        ChunkDeadLetterStatus.RESOLVED
    }


async def test_the_indexing_stage_replays_only_indexing_rows(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    embedding_document = await _document_with_failed_embedding(
        db_session,
        session_factory,
        search_index,
        embedding_provider,
        caller,
        _ONE_CHUNK,
    )
    indexing_document = await _document_with_failed_indexing(
        db_session, search_index, caller
    )

    await _replay(
        session_factory, search_index, embedding_provider, stage=IngestionStage.INDEXING
    )

    assert {d.status for d in await _dead_letters(db_session, indexing_document)} == {
        ChunkDeadLetterStatus.RESOLVED
    }
    assert {d.status for d in await _dead_letters(db_session, embedding_document)} == {
        ChunkDeadLetterStatus.OPEN
    }
    assert embedding_provider.embed_calls == 0


async def test_an_indexing_only_replay_needs_no_embedding_provider(
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
) -> None:
    document_id = await _document_with_failed_indexing(db_session, search_index, caller)

    await _replay(session_factory, search_index, None, stage=IngestionStage.INDEXING)

    assert {d.status for d in await _dead_letters(db_session, document_id)} == {
        ChunkDeadLetterStatus.RESOLVED
    }


async def test_replaying_embedding_rows_without_a_provider_is_refused(
    session_factory: async_sessionmaker,
    search_index: FakeSearchIndex,
) -> None:
    with pytest.raises(EmbeddingProviderRequiredError):
        await _replay(session_factory, search_index, None)
