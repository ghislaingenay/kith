"""Tests for #69: `make embed-documents` adds `embed_document` jobs for the
Documents waiting at `embedding` (ADR-0014). Documents are put in their states
through `ingest_document` with a scripted `FakeSearchIndex`; the backlog is
then enqueued as a function against a fresh `FakeJobQueue`. The function is
given no embedding provider, which is how the tests show it never calls one."""

import uuid
from collections.abc import AsyncIterator

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from documents.config import IngestionSettings
from documents.embed_backlog import enqueue_embedding_backlog
from documents.ingest import ingest_document
from documents.keys import pending_upload_key
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.documents.conftest import (
    Caller,
    fast_retry_handler,
    finalize_upload,
    init_upload,
    make_text_pdf,
)
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
def backlog_queue() -> FakeJobQueue:
    """Apart from the `job_queue` the upload API enqueues `ingest_document`
    on, so it holds only what the backlog command adds."""
    return FakeJobQueue()


async def _ingest(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    text: str | list[str],
    index: FakeSearchIndex | None = None,
    settings: IngestionSettings | None = None,
) -> uuid.UUID:
    """Ingests a Document of one page per text. By default it ends waiting at `embedding`;
    its own embed job goes to a queue nobody reads, as for a Document ingested
    before this phase."""
    pdf = make_text_pdf([text] if isinstance(text, str) else text)
    upload_id = (await init_upload(client, pdf)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), pdf)
    document_id = uuid.UUID((await finalize_upload(client, upload_id)).json()["id"])
    await ingest_document(
        {
            "db_session_factory": session_factory,
            "storage_provider": storage,
            "ingestion_settings": settings or IngestionSettings(),
            "search_index": index or FakeSearchIndex(),
            "retry_handler": fast_retry_handler(),
            "job_queue": FakeJobQueue(),
        },
        document_id=str(document_id),
        tenant_id=str(caller.tenant_id),
    )
    return document_id


def _job(caller: Caller, document_id: uuid.UUID) -> EnqueuedJob:
    return EnqueuedJob(
        queue="ingest",
        function="embed_document",
        payload={"document_id": str(document_id), "tenant_id": str(caller.tenant_id)},
        job_id=f"embed:{document_id}",
    )


async def test_every_document_waiting_at_embedding_gets_a_job_and_no_other_does(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    backlog_queue: FakeJobQueue,
) -> None:
    first = await _ingest(client, storage, caller, session_factory, "Alpha page.")
    second = await _ingest(client, storage, caller, session_factory, "Bravo page.")
    down = FakeSearchIndex()
    down.down = True
    await _ingest(client, storage, caller, session_factory, "Charlie page.", down)
    deleted = await _ingest(client, storage, caller, session_factory, "Delta page.")
    assert (await client.delete(f"/api/v1/documents/{deleted}")).is_success

    count = await enqueue_embedding_backlog(session_factory, backlog_queue)

    assert count == 2
    assert sorted(backlog_queue.jobs, key=lambda job: job.job_id) == sorted(
        [_job(caller, first), _job(caller, second)], key=lambda job: job.job_id
    )


async def test_a_partial_document_is_enqueued_too(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    backlog_queue: FakeJobQueue,
) -> None:
    # One page per batch: page 1 is indexed, page 2 fails all three attempts.
    some_refused = FakeSearchIndex()
    some_refused.index_outcomes = [True, False, False, False]
    partial = await _ingest(
        client,
        storage,
        caller,
        session_factory,
        ["Alpha page.", "Bravo page."],
        some_refused,
        IngestionSettings.model_validate({"INGESTION_INDEX_BATCH_SIZE": 1}),
    )

    count = await enqueue_embedding_backlog(session_factory, backlog_queue)

    assert count == 1
    assert backlog_queue.jobs == [_job(caller, partial)]


async def test_one_document_can_be_enqueued_alone(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    backlog_queue: FakeJobQueue,
) -> None:
    await _ingest(client, storage, caller, session_factory, "Alpha page.")
    second = await _ingest(client, storage, caller, session_factory, "Bravo page.")

    count = await enqueue_embedding_backlog(
        session_factory, backlog_queue, document_id=second
    )

    assert count == 1
    assert backlog_queue.jobs == [_job(caller, second)]


async def test_a_document_not_waiting_at_embedding_is_not_enqueued_by_id(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    backlog_queue: FakeJobQueue,
) -> None:
    down = FakeSearchIndex()
    down.down = True
    failed = await _ingest(
        client, storage, caller, session_factory, "Alpha page.", down
    )

    count = await enqueue_embedding_backlog(
        session_factory, backlog_queue, document_id=failed
    )

    assert count == 0
    assert backlog_queue.jobs == []


async def test_an_unknown_document_id_enqueues_nothing(
    session_factory: async_sessionmaker, backlog_queue: FakeJobQueue
) -> None:
    count = await enqueue_embedding_backlog(
        session_factory, backlog_queue, document_id=uuid.uuid4()
    )

    assert count == 0
    assert backlog_queue.jobs == []


async def test_running_it_twice_leaves_one_job_per_document(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    backlog_queue: FakeJobQueue,
) -> None:
    document_id = await _ingest(client, storage, caller, session_factory, "Alpha page.")

    await enqueue_embedding_backlog(session_factory, backlog_queue)
    await enqueue_embedding_backlog(session_factory, backlog_queue)

    assert backlog_queue.jobs == [_job(caller, document_id)]


async def test_with_nothing_waiting_it_enqueues_nothing(
    session_factory: async_sessionmaker, backlog_queue: FakeJobQueue
) -> None:
    assert await enqueue_embedding_backlog(session_factory, backlog_queue) == 0
    assert backlog_queue.jobs == []
