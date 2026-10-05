"""Tests for #66: when indexing finishes, `ingest_document` hands the Document
to the `embed_document` job through the job queue (ADR-0014). Same seam as the
other ingestion tests (real PDFs, `FakeStorageProvider`, real Postgres) with a
scripted `FakeSearchIndex` and a `FakeJobQueue`."""

import uuid
from collections.abc import AsyncIterator

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from documents.config import IngestionSettings
from documents.ingest import ingest_document
from documents.keys import pending_upload_key
from httpx import AsyncClient

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

_THREE_PAGES = make_text_pdf(["First page.", "Second page.", "Third page."])


@pytest.fixture
def fake_index() -> FakeSearchIndex:
    return FakeSearchIndex()


@pytest.fixture
async def ingest_ctx(
    _database_url: str,
    storage: FakeStorageProvider,
    fake_index: FakeSearchIndex,
    job_queue: FakeJobQueue,
) -> AsyncIterator[dict]:
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield {
        "db_session_factory": create_session_factory(engine),
        "storage_provider": storage,
        # One Chunk per page, one page per batch.
        "ingestion_settings": IngestionSettings.model_validate(
            {"INGESTION_INDEX_BATCH_SIZE": 1}
        ),
        "search_index": fake_index,
        "retry_handler": fast_retry_handler(),
        "job_queue": job_queue,
    }
    await engine.dispose()


async def _upload_and_ingest(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    ctx: dict,
    pdf: bytes,
) -> uuid.UUID:
    upload_id = (await init_upload(client, pdf)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), pdf)
    document_id = uuid.UUID((await finalize_upload(client, upload_id)).json()["id"])
    await ingest_document(
        ctx, document_id=str(document_id), tenant_id=str(caller.tenant_id)
    )
    return document_id


def _embed_jobs(job_queue: FakeJobQueue) -> list[EnqueuedJob]:
    return [job for job in job_queue.jobs if job.function == "embed_document"]


async def test_a_document_waiting_at_embedding_gets_an_embed_job(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    ingest_ctx: dict,
    job_queue: FakeJobQueue,
) -> None:
    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, make_text_pdf(["Known page text."])
    )

    assert _embed_jobs(job_queue) == [
        EnqueuedJob(
            queue="ingest",
            function="embed_document",
            payload={
                "document_id": str(document_id),
                "tenant_id": str(caller.tenant_id),
            },
            job_id=f"embed:{document_id}",
        )
    ]


async def test_a_partial_document_also_gets_an_embed_job(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
    job_queue: FakeJobQueue,
) -> None:
    # Page 1 works, page 2 fails all three attempts, page 3 works.
    fake_index.index_outcomes = [True, False, False, False, True]

    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, _THREE_PAGES
    )

    assert [job.job_id for job in _embed_jobs(job_queue)] == [f"embed:{document_id}"]


async def test_a_failed_document_gets_no_embed_job(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    ingest_ctx: dict,
    fake_index: FakeSearchIndex,
    job_queue: FakeJobQueue,
) -> None:
    fake_index.down = True

    await _upload_and_ingest(client, storage, caller, ingest_ctx, _THREE_PAGES)

    assert _embed_jobs(job_queue) == []
