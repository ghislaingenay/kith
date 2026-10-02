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
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.jobs.arq_queue import ArqJobQueue
from documents.config import IngestionSettings
from documents.ingest import ingest_document
from documents.keys import pending_upload_key
from documents.models import Document, IngestionStage, IngestionStatus
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents.conftest import (
    Caller,
    finalize_upload,
    init_upload,
    make_text_pdf,
)
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
) -> None:
    """Runs a real arq worker against `redis_settings` in burst mode: it
    processes whatever is already queued on `ingest`, then returns — a
    worker process, minus the part where it stays up forever."""

    async def startup(ctx: dict) -> None:
        engine = create_engine(DatabaseSettings(database_url=database_url))
        ctx["_engine"] = engine
        ctx["db_session_factory"] = create_session_factory(engine)
        ctx["storage_provider"] = storage_provider
        ctx["ingestion_settings"] = IngestionSettings()

    async def shutdown(ctx: dict) -> None:
        await ctx["_engine"].dispose()

    worker = Worker(
        functions=[ingest_document],
        queue_name="ingest",
        redis_settings=redis_settings,
        burst=True,
        poll_delay=0,
        on_startup=startup,
        on_shutdown=shutdown,
    )
    await worker.main()
    await worker.close()


async def test_an_enqueued_job_is_picked_up_and_executed_by_a_real_worker(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    _redis_settings: RedisSettings,
    _database_url: str,
) -> None:
    upload_id = (await init_upload(client, _PDF)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), _PDF)
    document_id = (await finalize_upload(client, upload_id)).json()["id"]

    await _run_ingest_worker_once(_redis_settings, _database_url, storage)

    document = (
        await db_session.execute(
            select(Document).where(Document.id == uuid.UUID(document_id))
        )
    ).scalar_one()
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.CHUNKING


async def test_a_job_for_a_document_already_past_uploaded_is_left_alone(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    _redis_settings: RedisSettings,
    _database_url: str,
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

    await _run_ingest_worker_once(_redis_settings, _database_url, storage)

    await db_session.refresh(document)
    assert document.ingestion_status == IngestionStatus.FAILED
    assert document.ingestion_stage is None
