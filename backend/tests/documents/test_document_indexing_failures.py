"""Tests for #52: indexing degrades in a defined way when the search store is
unavailable (ADR-0011). Same seam as the other ingestion tests (real PDFs,
`FakeStorageProvider`, real Postgres), with a scripted `FakeSearchIndex` and,
where the breaker matters, the real breaker around it on a fake clock."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from core.circuit_breaker.breaker import CircuitBreaker
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.search.circuit_breaker_index import CircuitBreakerSearchIndex
from core.search.exceptions import SearchError, SearchUnavailableError
from documents.config import IngestionSettings
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
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents.conftest import (
    Caller,
    fast_retry_handler,
    finalize_upload,
    init_upload,
    make_text_pdf,
)
from tests.support.fake_search_index import FakeSearchIndex
from tests.support.fake_storage import FakeStorageProvider

_THREE_PAGES = make_text_pdf(["First page.", "Second page.", "Third page."])


@pytest.fixture
def fake_index() -> FakeSearchIndex:
    return FakeSearchIndex()


@pytest.fixture
def breaker() -> CircuitBreaker:
    return CircuitBreaker(
        name="search",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(SearchUnavailableError,),
        clock=lambda: 0.0,
    )


@pytest.fixture
async def ingest_ctx(
    _database_url: str,
    storage: FakeStorageProvider,
    fake_index: FakeSearchIndex,
    breaker: CircuitBreaker,
) -> AsyncIterator[dict]:
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield {
        "db_session_factory": create_session_factory(engine),
        "storage_provider": storage,
        # One Chunk per page, one page per batch.
        "ingestion_settings": IngestionSettings.model_validate(
            {"INGESTION_INDEX_BATCH_SIZE": 1}
        ),
        "search_index": CircuitBreakerSearchIndex(fake_index, breaker),
        "retry_handler": fast_retry_handler(),
    }
    await engine.dispose()


async def _upload(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller, pdf: bytes
) -> uuid.UUID:
    upload_id = (await init_upload(client, pdf)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), pdf)
    return uuid.UUID((await finalize_upload(client, upload_id)).json()["id"])


async def _ingest(ctx: dict, caller: Caller, document_id: uuid.UUID) -> None:
    await ingest_document(
        ctx, document_id=str(document_id), tenant_id=str(caller.tenant_id)
    )


async def _document(db_session: AsyncSession, document_id: uuid.UUID) -> Document:
    db_session.expire_all()
    return (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()


async def _chunks(db_session: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
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
    return list(
        (
            await db_session.execute(
                select(ChunkDeadLetter)
                .where(ChunkDeadLetter.document_id == document_id)
                .order_by(ChunkDeadLetter.created_at, ChunkDeadLetter.attempts.desc())
            )
        ).scalars()
    )


async def test_a_batch_that_fails_twice_then_succeeds_is_indexed_with_no_failure(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
) -> None:
    document_id = await _upload(
        client, storage, caller, make_text_pdf(["Known page text."])
    )
    fake_index.index_outcomes = [False, False, True]

    await _ingest(ingest_ctx, caller, document_id)

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.EMBEDDING
    assert document.ingestion_error is None
    assert fake_index.index_calls == 3
    assert [c.indexing_status for c in await _chunks(db_session, document_id)] == [
        ChunkStatus.DONE
    ]
    assert await _dead_letters(db_session, document_id) == []


async def test_a_batch_that_fails_three_times_is_recorded_and_the_job_does_not_raise(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
) -> None:
    document_id = await _upload(
        client, storage, caller, make_text_pdf(["Known page text."])
    )
    fake_index.down = True

    await _ingest(ingest_ctx, caller, document_id)

    (chunk,) = await _chunks(db_session, document_id)
    assert chunk.indexing_status == ChunkStatus.FAILED
    assert chunk.indexing_error
    (chunk_dead_letter,) = await _dead_letters(db_session, document_id)
    assert chunk_dead_letter.tenant_id == caller.tenant_id
    assert chunk_dead_letter.stage == IngestionStage.INDEXING
    assert chunk_dead_letter.chunk_ids == [chunk.id]
    assert chunk_dead_letter.error == chunk.indexing_error
    assert chunk_dead_letter.attempts == 3
    assert chunk_dead_letter.status == ChunkDeadLetterStatus.OPEN
    assert chunk_dead_letter.resolved_at is None
    assert fake_index.index_calls == 3


async def test_a_document_with_some_failed_chunks_is_partial(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
) -> None:
    document_id = await _upload(client, storage, caller, _THREE_PAGES)
    # Page 1 works, page 2 fails all three attempts, page 3 works.
    fake_index.index_outcomes = [True, False, False, False, True]

    await _ingest(ingest_ctx, caller, document_id)

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PARTIAL
    assert document.ingestion_error
    assert [c.indexing_status for c in await _chunks(db_session, document_id)] == [
        ChunkStatus.DONE,
        ChunkStatus.FAILED,
        ChunkStatus.DONE,
    ]
    assert len(await _dead_letters(db_session, document_id)) == 1


async def test_a_document_with_no_indexed_chunks_is_failed_with_a_readable_reason(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
) -> None:
    document_id = await _upload(client, storage, caller, _THREE_PAGES)
    fake_index.down = True

    await _ingest(ingest_ctx, caller, document_id)

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.FAILED
    assert document.ingestion_stage == IngestionStage.INDEXING
    assert "search service could not index" in document.ingestion_error
    assert "SearchUnavailableError" not in document.ingestion_error


async def test_after_five_failures_further_calls_fail_fast_and_are_not_retried(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
) -> None:
    document_id = await _upload(client, storage, caller, _THREE_PAGES)
    fake_index.down = True

    await _ingest(ingest_ctx, caller, document_id)

    # Page 1: three attempts. Page 2: two more, the fifth opens the breaker,
    # so its third attempt is rejected unretried. Page 3: rejected at once.
    assert fake_index.index_calls == 5
    assert [d.attempts for d in await _dead_letters(db_session, document_id)] == [
        3,
        2,
        0,
    ]
    assert [c.indexing_status for c in await _chunks(db_session, document_id)] == [
        ChunkStatus.FAILED
    ] * 3
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )


async def test_an_unavailable_store_on_cleanup_fails_every_chunk_without_indexing(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
) -> None:
    document_id = await _upload(client, storage, caller, _THREE_PAGES)
    fake_index.delete_down = True

    await _ingest(ingest_ctx, caller, document_id)

    assert fake_index.index_calls == 0
    (chunk_dead_letter,) = await _dead_letters(db_session, document_id)
    assert len(chunk_dead_letter.chunk_ids) == 3
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )


async def test_a_failure_outside_the_search_store_returns_to_uploaded_and_raises(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
) -> None:
    document_id = await _upload(
        client, storage, caller, make_text_pdf(["Known page text."])
    )
    fake_index.crash_with = ConnectionError("database went away")

    with pytest.raises(ConnectionError):
        await _ingest(ingest_ctx, caller, document_id)

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.UPLOADED
    assert document.ingestion_stage is None
    assert await _dead_letters(db_session, document_id) == []


async def test_a_batch_the_store_rejects_is_recorded_without_retries_and_without_raising(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
) -> None:
    document_id = await _upload(
        client, storage, caller, make_text_pdf(["Known page text."])
    )
    fake_index.crash_with = SearchError("mapping conflict")

    await _ingest(ingest_ctx, caller, document_id)

    assert fake_index.index_calls == 1
    (dead_letter,) = await _dead_letters(db_session, document_id)
    assert dead_letter.attempts == 1
    assert "mapping conflict" in dead_letter.error
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )


async def test_failures_are_timestamped_when_they_happen_not_when_the_slow_call_began(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
) -> None:
    document_id = await _upload(
        client, storage, caller, make_text_pdf(["Known page text."])
    )
    fake_index.down = True
    fake_index.delay_seconds = 0.3
    started = datetime.now(UTC)

    await _ingest(ingest_ctx, caller, document_id)

    # Three attempts of 0.3 s each came before the failure was written.
    slow = started + timedelta(seconds=0.9)
    (chunk,) = await _chunks(db_session, document_id)
    assert chunk.updated_at >= slow
    (chunk_dead_letter,) = await _dead_letters(db_session, document_id)
    assert chunk_dead_letter.created_at >= slow
