"""Tests for #121: `make rebuild-index` refills the search index from Postgres
after it is lost (ADR-0019). Documents are put in their states through the
upload API, `ingest_document` and `embed_document`; the index is then lost
by emptying the fake, and the rebuild is called as a function against a fresh
`FakeJobQueue`."""

import uuid
from collections.abc import AsyncIterator

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from documents.config import IngestionSettings
from documents.embed import embed_document
from documents.exceptions import IngestionInProgressError
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
from documents.rebuild_index import RebuildResult, rebuild_index
from httpx import AsyncClient
from scripts import rebuild_index as script
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.documents.conftest import (
    Caller,
    fast_retry_handler,
    finalize_upload,
    init_upload,
    make_image_only_pdf,
    make_text_pdf,
)
from tests.support.fake_embedding_provider import FakeEmbeddingProvider
from tests.support.fake_job_queue import EnqueuedJob, FakeJobQueue
from tests.support.fake_search_index import FakeSearchIndex
from tests.support.fake_storage import FakeStorageProvider


@pytest.fixture
async def session_factory(
    _database_url: str, db_session: AsyncSession
) -> AsyncIterator[async_sessionmaker]:
    """Depends on `db_session` for the schema, which it creates and drops."""
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
def rebuild_queue() -> FakeJobQueue:
    """Apart from the `job_queue` the upload API enqueues `ingest_document`
    on, so it holds only what the rebuild adds."""
    return FakeJobQueue()


async def _upload(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    pages: list[str],
) -> uuid.UUID:
    """A Document left at `uploaded`, its `ingest_document` job not run."""
    pdf = make_text_pdf(pages)
    upload_id = (await init_upload(client, pdf)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), pdf)
    return uuid.UUID((await finalize_upload(client, upload_id)).json()["id"])


async def _ready(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    index: FakeSearchIndex,
    pages: list[str],
) -> uuid.UUID:
    """A Document ingested and embedded: `ready`, every Chunk indexed and
    embedded. Its own jobs go to a queue nobody reads."""
    document_id = await _upload(client, storage, caller, pages)
    await ingest_document(
        {
            "db_session_factory": session_factory,
            "storage_provider": storage,
            "ingestion_settings": IngestionSettings(),
            "search_index": index,
            "retry_handler": fast_retry_handler(),
            "job_queue": FakeJobQueue(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    await embed_document(
        {
            "db_session_factory": session_factory,
            "ingestion_settings": IngestionSettings(),
            "search_index": index,
            "embedding_provider": FakeEmbeddingProvider(),
            "retry_handler": fast_retry_handler(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    return document_id


async def _rebuild(
    session_factory: async_sessionmaker,
    index: FakeSearchIndex,
    queue: FakeJobQueue,
    settings: IngestionSettings | None = None,
) -> RebuildResult:
    return await rebuild_index(
        session_factory,
        index,
        queue,
        fast_retry_handler(),
        settings or IngestionSettings(),
    )


def _lose(index: FakeSearchIndex) -> None:
    """The index is gone, as after losing the OpenSearch volume."""
    index.indexed = []
    index.embeddings = {}
    index.index_exists = False
    index.pipeline_exists = False


def _job(caller: Caller, document_id: uuid.UUID) -> EnqueuedJob:
    return EnqueuedJob(
        queue="ingest",
        function="embed_document",
        payload={"document_id": str(document_id), "tenant_id": str(caller.tenant_id)},
        job_id=f"embed:{document_id}",
    )


async def _document(db_session: AsyncSession, document_id: uuid.UUID) -> Document:
    db_session.expire_all()
    return await db_session.get_one(Document, document_id)


async def _chunks(db_session: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
    db_session.expire_all()
    result = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.ordinal)
    )
    return list(result.scalars())


async def _dead_letters(
    db_session: AsyncSession, document_id: uuid.UUID
) -> list[ChunkDeadLetter]:
    db_session.expire_all()
    result = await db_session.execute(
        select(ChunkDeadLetter).where(ChunkDeadLetter.document_id == document_id)
    )
    return list(result.scalars())


async def test_a_lost_index_is_refilled_with_every_live_documents_chunks(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    first = await _ready(
        client, storage, caller, session_factory, fake_search_index, ["Alpha."]
    )
    second = await _ready(
        client,
        storage,
        caller,
        session_factory,
        fake_search_index,
        ["Bravo.", "Charlie."],
    )
    _lose(fake_search_index)

    result = await _rebuild(session_factory, fake_search_index, rebuild_queue)

    assert result == RebuildResult(
        documents_reindexed=2, documents_queued_for_embedding=2, chunks_dead_lettered=0
    )
    assert fake_search_index.recreate_calls == 1
    assert fake_search_index.index_exists
    expected_ids = {
        chunk.id
        for document_id in (first, second)
        for chunk in await _chunks(db_session, document_id)
    }
    assert {chunk.id for chunk in fake_search_index.indexed} == expected_ids
    assert len(fake_search_index.indexed) == 3


async def test_embedding_is_reset_and_queued_once_per_reindexed_document(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    document_id = await _ready(
        client,
        storage,
        caller,
        session_factory,
        fake_search_index,
        ["Alpha.", "Bravo."],
    )
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.READY
    )
    _lose(fake_search_index)

    await _rebuild(session_factory, fake_search_index, rebuild_queue)

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.EMBEDDING
    chunks = await _chunks(db_session, document_id)
    assert {chunk.indexing_status for chunk in chunks} == {ChunkStatus.DONE}
    assert {chunk.embedding_status for chunk in chunks} == {ChunkStatus.PENDING}
    assert rebuild_queue.jobs == [_job(caller, document_id)]


async def test_a_deleted_document_stays_out_of_the_index(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    live = await _ready(
        client, storage, caller, session_factory, fake_search_index, ["Alpha."]
    )
    deleted = await _ready(
        client, storage, caller, session_factory, fake_search_index, ["Bravo."]
    )
    assert (await client.delete(f"/api/v1/documents/{deleted}")).is_success
    _lose(fake_search_index)

    result = await _rebuild(session_factory, fake_search_index, rebuild_queue)

    assert result.documents_reindexed == 1
    assert {chunk.document_id for chunk in fake_search_index.indexed} == {live}
    assert rebuild_queue.jobs == [_job(caller, live)]
    assert (await _document(db_session, deleted)).ingestion_status == (
        IngestionStatus.DELETED
    )


async def test_a_document_still_earlier_in_ingestion_is_untouched(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    uploaded = await _upload(client, storage, caller, ["Alpha."])

    result = await _rebuild(session_factory, fake_search_index, rebuild_queue)

    assert result == RebuildResult(
        documents_reindexed=0, documents_queued_for_embedding=0, chunks_dead_lettered=0
    )
    document = await _document(db_session, uploaded)
    assert document.ingestion_status == IngestionStatus.UPLOADED
    assert document.ingestion_stage is None
    assert fake_search_index.indexed == []
    assert rebuild_queue.jobs == []


async def test_a_failing_index_batch_is_dead_lettered_as_in_ingestion(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    document_id = await _ready(
        client,
        storage,
        caller,
        session_factory,
        fake_search_index,
        ["Alpha.", "Bravo."],
    )
    _lose(fake_search_index)
    # One Chunk per batch: the first is indexed, the second fails all three
    # attempts.
    fake_search_index.index_outcomes = [True, False, False, False]

    result = await _rebuild(
        session_factory,
        fake_search_index,
        rebuild_queue,
        IngestionSettings.model_validate({"INGESTION_INDEX_BATCH_SIZE": 1}),
    )

    assert result == RebuildResult(
        documents_reindexed=1, documents_queued_for_embedding=1, chunks_dead_lettered=1
    )
    first, second = await _chunks(db_session, document_id)
    assert first.indexing_status == ChunkStatus.DONE
    assert second.indexing_status == ChunkStatus.FAILED
    dead_letter = (
        await db_session.execute(
            select(ChunkDeadLetter).where(ChunkDeadLetter.document_id == document_id)
        )
    ).scalar_one()
    assert dead_letter.stage == IngestionStage.INDEXING
    assert dead_letter.chunk_ids == [second.id]
    assert dead_letter.attempts == 3
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PARTIAL
    )
    assert rebuild_queue.jobs == [_job(caller, document_id)]


async def test_a_document_whose_every_batch_fails_is_not_queued_for_embedding(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    document_id = await _ready(
        client, storage, caller, session_factory, fake_search_index, ["Alpha."]
    )
    _lose(fake_search_index)
    fake_search_index.down = True

    result = await _rebuild(session_factory, fake_search_index, rebuild_queue)

    assert result == RebuildResult(
        documents_reindexed=1, documents_queued_for_embedding=0, chunks_dead_lettered=1
    )
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )
    assert rebuild_queue.jobs == []


async def test_running_it_twice_gives_the_same_result(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    document_id = await _ready(
        client,
        storage,
        caller,
        session_factory,
        fake_search_index,
        ["Alpha.", "Bravo."],
    )
    _lose(fake_search_index)

    first = await _rebuild(session_factory, fake_search_index, rebuild_queue)
    indexed_after_first = sorted(chunk.id for chunk in fake_search_index.indexed)
    rebuild_queue.jobs = []  # the worker took the first run's jobs
    second = await _rebuild(session_factory, fake_search_index, rebuild_queue)

    assert first == second
    assert sorted(chunk.id for chunk in fake_search_index.indexed) == (
        indexed_after_first
    )
    assert rebuild_queue.jobs == [_job(caller, document_id)]
    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.EMBEDDING


@pytest.mark.parametrize("answer", ["", "no", "y"])
async def test_the_script_refuses_to_run_without_confirmation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], answer: str
) -> None:
    async def must_not_run(*args: object) -> RebuildResult:
        raise AssertionError("rebuild_index ran without confirmation")

    monkeypatch.setattr(script, "rebuild_index", must_not_run)
    monkeypatch.setattr("sys.argv", ["rebuild_index"])
    monkeypatch.setattr("builtins.input", lambda prompt: answer)

    await script.main()

    assert capsys.readouterr().out == "Nothing was changed\n"


async def test_a_document_deleted_while_it_runs_is_skipped(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    first = await _ready(
        client, storage, caller, session_factory, fake_search_index, ["Alpha."]
    )
    second = await _ready(
        client, storage, caller, session_factory, fake_search_index, ["Bravo."]
    )
    _lose(fake_search_index)
    delete_document_chunks = fake_search_index.delete_document_chunks

    async def delete_second_while_first_is_indexed(
        *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        if document_id == first:
            assert (await client.delete(f"/api/v1/documents/{second}")).is_success
        await delete_document_chunks(tenant_id=tenant_id, document_id=document_id)

    fake_search_index.delete_document_chunks = delete_second_while_first_is_indexed

    result = await _rebuild(session_factory, fake_search_index, rebuild_queue)

    assert result.documents_reindexed == 1
    assert {chunk.document_id for chunk in fake_search_index.indexed} == {first}
    assert rebuild_queue.jobs == [_job(caller, first)]
    assert (await _document(db_session, second)).ingestion_status == (
        IngestionStatus.DELETED
    )


async def test_it_refuses_to_start_while_the_ingest_queue_has_work(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    document_id = await _ready(
        client, storage, caller, session_factory, fake_search_index, ["Alpha."]
    )
    # A job queued, waiting to retry or running: it could write to the
    # Document while the rebuild does.
    await rebuild_queue.enqueue(
        "ingest", "embed_document", {}, job_id=f"embed:{document_id}"
    )

    with pytest.raises(IngestionInProgressError):
        await _rebuild(session_factory, fake_search_index, rebuild_queue)

    assert fake_search_index.recreate_calls == 0
    assert len(fake_search_index.indexed) == 1
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.READY
    )


async def test_open_dead_letters_from_before_are_closed(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    """The rebuild redoes every Chunk's indexing and embedding, so a replay
    of the old rows would only embed Chunks a second time."""
    settings = IngestionSettings.model_validate(
        {"INGESTION_INDEX_BATCH_SIZE": 1, "INGESTION_EMBED_BATCH_MAX_CHUNKS": 1}
    )
    document_id = await _upload(
        client, storage, caller, ["Alpha.", "Bravo.", "Charlie."]
    )
    # Page 3's batch fails all three attempts: an open `indexing` row.
    fake_search_index.index_outcomes = [True, True, False, False, False]
    await ingest_document(
        {
            "db_session_factory": session_factory,
            "storage_provider": storage,
            "ingestion_settings": settings,
            "search_index": fake_search_index,
            "retry_handler": fast_retry_handler(),
            "job_queue": FakeJobQueue(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    # Voyage refuses page 1's Chunk three times: an open `embedding` row.
    # Page 2's is embedded, so the Document stays `partial`.
    voyage = FakeEmbeddingProvider()
    voyage.embed_outcomes = [False, False, False, True]
    await embed_document(
        {
            "db_session_factory": session_factory,
            "ingestion_settings": settings,
            "search_index": fake_search_index,
            "embedding_provider": voyage,
            "retry_handler": fast_retry_handler(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    old_rows = await _dead_letters(db_session, document_id)
    assert {row.stage for row in old_rows} == {
        IngestionStage.INDEXING,
        IngestionStage.EMBEDDING,
    }
    assert {row.status for row in old_rows} == {ChunkDeadLetterStatus.OPEN}
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.PARTIAL
    )
    _lose(fake_search_index)

    result = await _rebuild(session_factory, fake_search_index, rebuild_queue, settings)

    assert result.chunks_dead_lettered == 0
    rows = await _dead_letters(db_session, document_id)
    assert len(rows) == 2
    assert {row.status for row in rows} == {ChunkDeadLetterStatus.RESOLVED}
    assert all(row.resolved_at is not None for row in rows)
    chunks = await _chunks(db_session, document_id)
    assert {chunk.indexing_status for chunk in chunks} == {ChunkStatus.DONE}
    assert {chunk.embedding_status for chunk in chunks} == {ChunkStatus.PENDING}
    assert rebuild_queue.jobs == [_job(caller, document_id)]


async def test_a_document_failed_at_embedding_is_rebuilt(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    """Its Chunks were in the lost index; skipped, it could never be made
    searchable again."""
    document_id = await _upload(client, storage, caller, ["Alpha."])
    await ingest_document(
        {
            "db_session_factory": session_factory,
            "storage_provider": storage,
            "ingestion_settings": IngestionSettings(),
            "search_index": fake_search_index,
            "retry_handler": fast_retry_handler(),
            "job_queue": FakeJobQueue(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    voyage_down = FakeEmbeddingProvider()
    voyage_down.is_down = True
    await embed_document(
        {
            "db_session_factory": session_factory,
            "ingestion_settings": IngestionSettings(),
            "search_index": fake_search_index,
            "embedding_provider": voyage_down,
            "retry_handler": fast_retry_handler(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    assert (await _document(db_session, document_id)).ingestion_status == (
        IngestionStatus.FAILED
    )
    _lose(fake_search_index)

    result = await _rebuild(session_factory, fake_search_index, rebuild_queue)

    assert result.documents_reindexed == 1
    assert {chunk.document_id for chunk in fake_search_index.indexed} == {document_id}
    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.EMBEDDING
    assert document.ingestion_error is None
    assert rebuild_queue.jobs == [_job(caller, document_id)]


async def test_a_document_failed_with_no_chunks_is_untouched(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
    rebuild_queue: FakeJobQueue,
) -> None:
    pdf = make_image_only_pdf()
    upload_id = (await init_upload(client, pdf)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), pdf)
    document_id = uuid.UUID((await finalize_upload(client, upload_id)).json()["id"])
    await ingest_document(
        {
            "db_session_factory": session_factory,
            "storage_provider": storage,
            "ingestion_settings": IngestionSettings(),
            "search_index": fake_search_index,
            "retry_handler": fast_retry_handler(),
            "job_queue": FakeJobQueue(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    before = await _document(db_session, document_id)
    assert before.ingestion_status == IngestionStatus.FAILED
    error = before.ingestion_error

    result = await _rebuild(session_factory, fake_search_index, rebuild_queue)

    assert result.documents_reindexed == 0
    after = await _document(db_session, document_id)
    assert after.ingestion_status == IngestionStatus.FAILED
    assert after.ingestion_error == error
    assert rebuild_queue.jobs == []
