"""Tests for `make clean-documents`: every Document, Chunk and Upload, their
files in storage and the search index are removed, and nothing else in storage.
Documents are put in place through the upload API and `ingest_document`; the
cleanup is then called as a function."""

import uuid
from collections.abc import AsyncIterator

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from documents.clean_documents import CleanResult, clean_documents
from documents.config import IngestionSettings
from documents.ingest import ingest_document
from documents.keys import document_key, pending_upload_key
from documents.models import ChunkDeadLetter, Chunk, Document, DocumentPage, Upload
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tests.documents.conftest import (
    Caller,
    fast_retry_handler,
    finalize_upload,
    init_upload,
    make_pdf,
    make_text_pdf,
)
from tests.support.fake_job_queue import FakeJobQueue
from tests.support.fake_search_index import FakeSearchIndex
from tests.support.fake_storage import FakeStorageProvider

_UNRELATED_KEY = "tenants/logos/acme.png"


@pytest.fixture
async def session_factory(
    _database_url: str, db_session: AsyncSession
) -> AsyncIterator[async_sessionmaker]:
    """Depends on `db_session` for the schema, which it creates and drops."""
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield create_session_factory(engine)
    await engine.dispose()


async def _ingested_document(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    session_factory: async_sessionmaker,
    index: FakeSearchIndex,
) -> uuid.UUID:
    pdf = make_text_pdf(["Known page text."])
    upload_id = (await init_upload(client, pdf)).json()["upload_id"]
    storage.put_object(pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), pdf)
    document_id = uuid.UUID((await finalize_upload(client, upload_id)).json()["id"])
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
    return document_id


async def _count(db_session: AsyncSession, model: type) -> int:
    db_session.expire_all()
    return (
        await db_session.execute(select(func.count()).select_from(model))
    ).scalar_one()


async def test_cleaning_removes_every_document_chunk_and_upload_and_their_files(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
) -> None:
    document_id = await _ingested_document(
        client, storage, caller, session_factory, fake_search_index
    )
    unfinished_pdf = make_pdf()
    unfinished_upload_id = (await init_upload(client, unfinished_pdf, "b.pdf")).json()[
        "upload_id"
    ]
    unfinished_key = pending_upload_key(
        caller.tenant_id, uuid.UUID(unfinished_upload_id)
    )
    storage.put_object(unfinished_key, unfinished_pdf)
    storage.put_object(_UNRELATED_KEY, b"png")
    assert document_key(caller.tenant_id, document_id) in storage.keys
    assert await _count(db_session, Chunk) > 0

    result = await clean_documents(session_factory, storage, fake_search_index)

    assert result == CleanResult(documents=1, uploads=2)
    for model in (Document, Chunk, DocumentPage, ChunkDeadLetter, Upload):
        assert await _count(db_session, model) == 0
    assert document_key(caller.tenant_id, document_id) in storage.deleted
    assert unfinished_key in storage.deleted
    assert _UNRELATED_KEY in storage.keys
    assert fake_search_index.recreate_calls == 1
    assert fake_search_index.indexed == []


async def test_cleaning_nothing_succeeds_and_still_recreates_the_index(
    storage: FakeStorageProvider,
    session_factory: async_sessionmaker,
    fake_search_index: FakeSearchIndex,
) -> None:
    result = await clean_documents(session_factory, storage, fake_search_index)

    assert result == CleanResult(documents=0, uploads=0)
    assert fake_search_index.recreate_calls == 1
