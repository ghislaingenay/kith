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
from documents.config import IngestionSettings
from documents.dead_letter_replay import replay_failed_batches
from documents.embed import embed_document
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
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.documents.conftest import (
    Caller,
    fast_retry_handler,
    finalize_upload,
    init_upload,
    make_text_pdf,
)
from tests.support.fake_embedding_provider import FakeEmbeddingProvider, vector_for
from tests.support.fake_job_queue import FakeJobQueue
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
            "job_queue": FakeJobQueue(),
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
    client: AsyncClient, db_session: AsyncSession, query: str
) -> list[int]:
    db_session.expire_all()
    response = await client.post("/api/v1/search", json={"query": query})
    return [result["page_number"] for result in response.json()["results"]]


async def test_replay_indexes_only_the_failed_chunks_and_resolves_their_rows(
    search_endpoint: None,
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    search_index: SearchIndex,
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PARTIAL
    )

    await replay_failed_batches(
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

    assert await _found_pages(client, db_session, "page") == [2, 3]
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
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )

    await replay_failed_batches(
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

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
    job_queue: FakeJobQueue,
) -> None:
    down = FakeSearchIndex()
    down.down = True
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, down
    )
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )

    await replay_failed_batches(
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

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
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    before = {d.id: d.attempts for d in await _dead_letters(db_session, document_id)}
    still_down = FakeSearchIndex()
    still_down.down = True

    await replay_failed_batches(
        session_factory,
        still_down,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

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
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    flaky = FakeSearchIndex()
    # Page 2's replay fails every attempt, page 3's works.
    flaky.index_outcomes = [False, False, False, True]

    await replay_failed_batches(
        session_factory, flaky, FakeEmbeddingProvider(), fast_retry_handler(), job_queue
    )

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
    job_queue: FakeJobQueue,
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
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
        document_id=second,
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
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )

    await replay_failed_batches(
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
        limit=1,
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
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    slow_store = FakeSearchIndex()
    slow_store.delay_seconds = 0.3
    started = datetime.now(UTC)

    await replay_failed_batches(
        session_factory,
        slow_store,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

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
    job_queue: FakeJobQueue,
) -> None:
    result = await replay_failed_batches(
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

    assert (result.resolved, result.failed) == (0, 0)


async def test_a_deleted_document_is_not_brought_back_by_replay(
    search_endpoint: None,
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    search_index: SearchIndex,
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    assert (await client.delete(f"/api/v1/documents/{document_id}")).is_success

    await replay_failed_batches(
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.DELETED
    )
    assert await _found_pages(client, db_session, "page") == []
    assert {d.status for d in await _dead_letters(db_session, document_id)} == {
        ChunkDeadLetterStatus.RESOLVED
    }


def _embed_job_ids(job_queue: FakeJobQueue) -> list[str]:
    return [j.job_id for j in job_queue.jobs if j.function == "embed_document"]


async def test_a_successful_indexing_replay_enqueues_embedding_for_the_document(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    search_index: SearchIndex,
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )

    await replay_failed_batches(
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

    # Two rows resolved for one Document: one job, thanks to the job id.
    assert job_queue.jobs[0].queue == "ingest"
    assert job_queue.jobs[0].payload == {
        "document_id": str(document_id),
        "tenant_id": str(caller.tenant_id),
    }
    assert _embed_job_ids(job_queue) == [f"embed:{document_id}"]


async def test_an_indexing_replay_that_fails_again_enqueues_no_embedding(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    job_queue: FakeJobQueue,
) -> None:
    await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )

    await replay_failed_batches(
        session_factory,
        _always_down(),
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

    assert _embed_job_ids(job_queue) == []


async def test_a_row_resolved_for_a_deleted_document_enqueues_no_embedding(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    search_index: SearchIndex,
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    assert (await client.delete(f"/api/v1/documents/{document_id}")).is_success

    await replay_failed_batches(
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

    assert _embed_job_ids(job_queue) == []


async def test_a_row_whose_chunks_no_longer_exist_enqueues_no_embedding(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    failing_index: FakeSearchIndex,
    search_index: SearchIndex,
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, failing_index
    )
    # The Document was chunked again, so the rows' Chunks are gone.
    async with session_factory() as session:
        await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
        await session.commit()

    await replay_failed_batches(
        session_factory,
        search_index,
        FakeEmbeddingProvider(),
        fast_retry_handler(),
        job_queue,
    )

    assert _embed_job_ids(job_queue) == []


async def test_a_replayed_document_gets_vectors_and_a_status_for_both_stages(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest_with_failed_batches(
        client, storage, caller, session_factory, _always_down()
    )
    healthy_index = FakeSearchIndex()
    embedding_provider = FakeEmbeddingProvider()
    retry_handler = fast_retry_handler()

    await replay_failed_batches(
        session_factory, healthy_index, embedding_provider, retry_handler, job_queue
    )
    # What the worker does with the job the replay queued.
    await embed_document(
        {
            "db_session_factory": session_factory,
            "ingestion_settings": IngestionSettings(),
            "search_index": healthy_index,
            "embedding_provider": embedding_provider,
            "retry_handler": retry_handler,
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )

    chunks = await _chunks(db_session, document_id)
    assert [c.embedding_status for c in chunks] == [ChunkStatus.DONE] * 3
    assert [healthy_index.embeddings[c.id] for c in chunks] == [
        vector_for(c.text) for c in chunks
    ]
    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.READY
    assert document.ingestion_error is None


def _always_down() -> FakeSearchIndex:
    index = FakeSearchIndex()
    index.down = True
    return index
