"""Tests for #53: replaying failed indexing batches (ADR-0011). Batches are
failed through `ingest_document` with a scripted `FakeSearchIndex`; replay is
then called as a function against the real OpenSearch container (success) or
a failing fake (repeat failure). Replay is given no storage, which is how the
tests show it never reads the PDF."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.search.provider import SearchIndex
from documents.chunk_search_service import ChunkSearchService
from documents.config import IngestionSettings
from documents.dead_letter_replay import replay_failed_batches
from documents.ingest import ingest_document
from documents.keys import pending_upload_key
from documents.models import (
    Chunk,
    ChunkDeadLetter,
    ChunkDeadLetterStatus,
    ChunkStatus,
    Document,
    IngestionStage,
    IngestionStatus,
)
from documents.repository import DocumentsRepository
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.documents.conftest import (
    Caller,
    fast_retry_handler,
    finalize_upload,
    init_upload,
    make_text_pdf,
)
from tests.support.fake_search_index import FakeSearchIndex
from tests.support.fake_storage import FakeStorageProvider

_THREE_PAGES = make_text_pdf(["Alpha page.", "Bravo page.", "Charlie page."])


@pytest.fixture
async def session_factory(_database_url: str) -> AsyncIterator[async_sessionmaker]:
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def failing_index() -> FakeSearchIndex:
    """What the first ingestion ran against: page 1 indexed, pages 2 and 3
    refused after the retries."""
    index = FakeSearchIndex()
    index.index_outcomes = [True, False, False, False, False, False, False]
    return index


async def _ingest_with_failed_batches(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    pdf: bytes = _THREE_PAGES,
) -> uuid.UUID:
    upload_id = (await init_upload(client, pdf)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), pdf)
    document_id = uuid.UUID((await finalize_upload(client, upload_id)).json()["id"])
    await ingest_document(
        {
            "db_session_factory": session_factory,
            "storage_provider": storage,
            "ingestion_settings": IngestionSettings.model_validate(
                {"INGESTION_INDEX_BATCH_SIZE": 1}
            ),
            "search_index": failing_index,
            "retry_handler": fast_retry_handler(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    return document_id


async def _document(db_session: AsyncSession, document_id: uuid.UUID) -> Document:
    db_session.expire_all()
    return (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()


async def _chunks(db_session: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                select(Chunk)
                .where(Chunk.document_id == document_id)
                .order_by(Chunk.ordinal)
            )
        ).scalars()
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
                .order_by(ChunkDeadLetter.created_at)
            )
        ).scalars()
    )


async def _found_pages(
    db_session: AsyncSession, search_index: SearchIndex, caller: Caller, query: str
) -> list[int]:
    hits = await ChunkSearchService(
        DocumentsRepository(db_session), search_index
    ).search(tenant_id=caller.tenant_id, query=query)
    return [hit.page_number for hit in hits]


async def test_replay_indexes_only_the_failed_chunks_and_resolves_their_rows(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    search_index: SearchIndex,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PARTIAL
    )

    await replay_failed_batches(session_factory, search_index, fast_retry_handler())

    assert await _found_pages(db_session, search_index, caller, "page") == [2, 3]
    assert [c.indexing_status for c in await _chunks(db_session, document_id)] == [
        ChunkStatus.DONE
    ] * 3
    assert [d.status for d in await _dead_letters(db_session, document_id)] == [
        ChunkDeadLetterStatus.RESOLVED
    ] * 2
    assert all(
        d.resolved_at is not None for d in await _dead_letters(db_session, document_id)
    )


async def test_after_replay_the_document_is_back_to_processing_at_embedding(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    search_index: SearchIndex,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )

    await replay_failed_batches(session_factory, search_index, fast_retry_handler())

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.EMBEDDING
    assert document.ingestion_error is None


async def test_a_document_with_no_indexed_chunks_also_recovers(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: SearchIndex,
) -> None:
    down = FakeSearchIndex()
    down.down = True
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, down
    )
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )

    await replay_failed_batches(session_factory, search_index, fast_retry_handler())

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.EMBEDDING
    assert document.ingestion_error is None


async def test_a_batch_that_fails_again_stays_open_with_more_attempts(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    before = {d.id: d.attempts for d in await _dead_letters(db_session, document_id)}
    still_down = FakeSearchIndex()
    still_down.down = True

    await replay_failed_batches(session_factory, still_down, fast_retry_handler())

    after = await _dead_letters(db_session, document_id)
    assert [d.status for d in after] == [ChunkDeadLetterStatus.OPEN] * 2
    assert all(d.attempts > before[d.id] for d in after)
    assert all(d.resolved_at is None for d in after)
    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PARTIAL
    assert [c.indexing_status for c in await _chunks(db_session, document_id)] == [
        ChunkStatus.DONE,
        ChunkStatus.FAILED,
        ChunkStatus.FAILED,
    ]


async def test_a_repeat_failure_does_not_stop_the_other_rows(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    flaky = FakeSearchIndex()
    # Page 2's replay fails every attempt, page 3's works.
    flaky.index_outcomes = [False, False, False, True]

    await replay_failed_batches(session_factory, flaky, fast_retry_handler())

    assert [d.status for d in await _dead_letters(db_session, document_id)] == [
        ChunkDeadLetterStatus.OPEN,
        ChunkDeadLetterStatus.RESOLVED,
    ]
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PARTIAL
    )


async def test_replay_can_be_limited_to_one_document(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    search_index: SearchIndex,
) -> None:
    first = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, _always_down()
    )
    second = await _ingest_with_failed_batches(
        client,
        storage,
        caller,
        session_factory,
        _always_down(),
        make_text_pdf(["Delta page."]),
    )

    await replay_failed_batches(
        session_factory, search_index, fast_retry_handler(), document_id=second
    )

    assert {d.status for d in await _dead_letters(db_session, first)} == {
        ChunkDeadLetterStatus.OPEN
    }
    assert {d.status for d in await _dead_letters(db_session, second)} == {
        ChunkDeadLetterStatus.RESOLVED
    }


async def test_replay_can_be_limited_to_a_number_of_rows_oldest_first(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    search_index: SearchIndex,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )

    await replay_failed_batches(
        session_factory, search_index, fast_retry_handler(), limit=1
    )

    assert [d.status for d in await _dead_letters(db_session, document_id)] == [
        ChunkDeadLetterStatus.RESOLVED,
        ChunkDeadLetterStatus.OPEN,
    ]
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PARTIAL
    )


async def test_replay_timestamps_are_taken_when_the_slow_call_returns(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    slow_store = FakeSearchIndex()
    slow_store.delay_seconds = 0.3
    started = datetime.now(UTC)

    await replay_failed_batches(session_factory, slow_store, fast_retry_handler())

    # Two rows, one 0.3 s call each, so the second finishes 0.6 s in.
    done = started + timedelta(seconds=0.6)
    rows = await _dead_letters(db_session, document_id)
    assert all(row.resolved_at is not None for row in rows)
    assert max(row.resolved_at for row in rows) >= done
    assert all(
        chunk.updated_at >= started + timedelta(seconds=0.3)
        for chunk in (await _chunks(db_session, document_id))[1:]
    )


async def test_replay_with_no_open_rows_does_nothing_and_succeeds(
    caller: Caller,
    session_factory: async_sessionmaker,
    search_index: SearchIndex,
) -> None:
    result = await replay_failed_batches(
        session_factory, search_index, fast_retry_handler()
    )

    assert (result.resolved, result.failed) == (0, 0)


async def test_a_deleted_document_is_not_brought_back_by_replay(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    search_index: SearchIndex,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    assert (await client.delete(f"/api/v1/documents/{document_id}")).is_success

    await replay_failed_batches(session_factory, search_index, fast_retry_handler())

    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.DELETED
    )
    assert await _found_pages(db_session, search_index, caller, "page") == []
    assert {d.status for d in await _dead_letters(db_session, document_id)} == {
        ChunkDeadLetterStatus.RESOLVED
    }


def _always_down() -> FakeSearchIndex:
    index = FakeSearchIndex()
    index.down = True
    return index
