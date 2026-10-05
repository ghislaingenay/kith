"""Proves the wiring for #39: a job enqueued by `finalize_upload` onto the
`ingest` queue is picked up by a running arq worker and executes
`ingest_document` — real Redis, real Postgres, and the real
`ArqJobQueue`/`arq.Worker` pair. Only the seams this domain's other upload
tests already fake (storage, the caller's identity) are faked here too."""

import uuid
from collections.abc import AsyncIterator

import pytest
from arq.connections import RedisSettings
from arq.worker import Worker
from core.search.provider import SearchIndex
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.jobs.arq_queue import ArqJobQueue
from documents.config import IngestionSettings
from documents.embed import embed_document
from documents.ingest import ingest_document
from documents.keys import pending_upload_key
from documents.models import Document, IngestionStage, IngestionStatus
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from structlog.testing import capture_logs

from tests.documents.conftest import (
    Caller,
    fast_retry_handler,
    finalize_upload,
    init_upload,
    make_text_pdf,
)
from tests.support.fake_embedding_provider import FakeEmbeddingProvider
from tests.support.fake_storage import FakeStorageProvider

_PDF = make_text_pdf(["First page.", "Second page."])


@pytest.fixture
async def job_queue(_redis_settings: RedisSettings) -> AsyncIterator[ArqJobQueue]:
    """A real `ArqJobQueue`, in place of the `FakeJobQueue` this domain's
    other tests use — this test exists to prove the real queue wiring, not
    to fake the part it's proving."""
    queue = ArqJobQueue(_redis_settings)
    yield queue
    await queue.close()


async def _run_ingest_worker_once(
    redis_settings: RedisSettings,
    database_url: str,
    storage_provider: FakeStorageProvider,
    search_index: SearchIndex,
    job_queue: ArqJobQueue,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    """Runs a real arq worker against `redis_settings` in burst mode: it
    processes whatever is already queued on `ingest`, including the
    `embed_document` job that ingestion adds, then returns — a worker
    process, minus the part where it stays up forever."""

    async def startup(ctx: dict) -> None:
        engine = create_engine(DatabaseSettings(database_url=database_url))
        ctx["_engine"] = engine
        ctx["db_session_factory"] = create_session_factory(engine)
        ctx["storage_provider"] = storage_provider
        ctx["ingestion_settings"] = IngestionSettings()
        ctx["search_index"] = search_index
        ctx["retry_handler"] = fast_retry_handler()
        ctx["job_queue"] = job_queue
        ctx["embedding_provider"] = embedding_provider

    async def shutdown(ctx: dict) -> None:
        await ctx["_engine"].dispose()

    worker = Worker(
        functions=[ingest_document, embed_document],
        queue_name="ingest",
        redis_settings=redis_settings,
        burst=True,
        poll_delay=0,
        on_startup=startup,
        on_shutdown=shutdown,
    )
    await worker.main()
    await worker.close()


@pytest.fixture
def embedding_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider()


async def test_an_uploaded_document_is_ingested_then_embedded_by_a_real_worker(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    _redis_settings: RedisSettings,
    _database_url: str,
    search_index: SearchIndex,
    job_queue: ArqJobQueue,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    upload_id = (await init_upload(client, _PDF)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), _PDF)
    document_id = (await finalize_upload(client, upload_id)).json()["id"]

    await _run_ingest_worker_once(
        _redis_settings,
        _database_url,
        storage,
        search_index,
        job_queue,
        embedding_provider,
    )

    document = (
        await db_session.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
    ).scalar_one()
    assert document.ingestion_status == IngestionStatus.READY
    assert document.ingestion_stage == IngestionStage.EMBEDDING
    assert len(embedding_provider.requests) == 1


async def test_the_same_embed_job_id_enqueued_twice_runs_once(
    caller: Caller,
    storage: FakeStorageProvider,
    _redis_settings: RedisSettings,
    _database_url: str,
    search_index: SearchIndex,
    job_queue: ArqJobQueue,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    # A Document that does not exist: the job only has to be seen running,
    # and logs `embed_document_missing` each time it does.
    document_id = uuid.uuid4()
    for _ in range(2):
        await job_queue.enqueue(
            "ingest",
            "embed_document",
            {"document_id": str(document_id), "tenant_id": str(caller.tenant_id)},
            job_id=f"embed:{document_id}",
        )

    with capture_logs() as logs:
        await _run_ingest_worker_once(
            _redis_settings,
            _database_url,
            storage,
            search_index,
            job_queue,
            embedding_provider,
        )

    runs = [log for log in logs if log["event"] == "embed_document_missing"]
    assert len(runs) == 1


async def test_a_job_for_a_document_already_past_uploaded_is_left_alone(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    _redis_settings: RedisSettings,
    _database_url: str,
    search_index: SearchIndex,
    job_queue: ArqJobQueue,
    embedding_provider: FakeEmbeddingProvider,
) -> None:
    upload_id = (await init_upload(client, _PDF)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), _PDF)
    document_id = (await finalize_upload(client, upload_id)).json()["id"]

    document = (
        await db_session.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
    ).scalar_one()
    document.ingestion_status = IngestionStatus.FAILED
    await db_session.commit()

    await _run_ingest_worker_once(
        _redis_settings,
        _database_url,
        storage,
        search_index,
        job_queue,
        embedding_provider,
    )

    await db_session.refresh(document)
    assert document.ingestion_status == IngestionStatus.FAILED
    assert document.ingestion_stage is None
