"""Tests for #51: ingested Chunks become keyword-searchable through the same
seam as the chunking tests (real PDFs, `FakeStorageProvider`, real Postgres),
against a real OpenSearch container."""

import uuid
from collections.abc import AsyncIterator

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.search.provider import SearchIndex
from documents.chunk_search_service import ChunkSearchService
from documents.config import IngestionSettings
from documents.ingest import ingest_document
from documents.keys import pending_upload_key
from documents.models import (
    Chunk,
    ChunkStatus,
    Document,
    IngestionStage,
    IngestionStatus,
)
from documents.repository import DocumentsRepository
from httpx import AsyncClient
from opensearchpy import AsyncOpenSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents.conftest import (
    Caller,
    finalize_upload,
    init_upload,
    make_text_pdf,
)
from tests.support.fake_storage import FakeStorageProvider


@pytest.fixture
async def ingest_ctx(
    _database_url: str, storage: FakeStorageProvider, search_index: SearchIndex
) -> AsyncIterator[dict]:
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield {
        "db_session_factory": create_session_factory(engine),
        "storage_provider": storage,
        "ingestion_settings": IngestionSettings(),
        "search_index": search_index,
    }
    await engine.dispose()


async def _upload_and_ingest(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    ctx: dict,
    pdf_bytes: bytes,
) -> uuid.UUID:
    upload_id = (await init_upload(client, pdf_bytes)).json()["upload_id"]
    storage.put_object(
        pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), pdf_bytes
    )
    document_id = uuid.UUID((await finalize_upload(client, upload_id)).json()["id"])
    await _ingest(ctx, caller, document_id)
    return document_id


async def _ingest(ctx: dict, caller: Caller, document_id: uuid.UUID) -> None:
    await ingest_document(
        ctx, document_id=str(document_id), tenant_id=str(caller.tenant_id)
    )


async def _search(
    db_session: AsyncSession, search_index: SearchIndex, caller: Caller, query: str
):
    db_session.expire_all()
    return await ChunkSearchService(
        DocumentsRepository(db_session), search_index
    ).search(tenant_id=caller.tenant_id, query=query)


async def test_an_ingested_document_is_found_by_keyword_ignoring_case_and_accents(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    search_index: SearchIndex,
) -> None:
    pdf = make_text_pdf(["Nothing here.", "Please send your résumé today."])
    document_id = await _upload_and_ingest(client, storage, caller, ingest_ctx, pdf)

    hits = await _search(db_session, search_index, caller, "RESUME")

    assert [(hit.document_id, hit.page_number) for hit in hits] == [(document_id, 2)]
    assert "résumé" in hits[0].text


async def test_index_documents_carry_the_chunk_rows_fields_and_no_vector(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    _opensearch_url: str,
) -> None:
    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, make_text_pdf(["Known page text."])
    )

    chunk = (
        await db_session.execute(select(Chunk).where(Chunk.document_id == document_id))
    ).scalar_one()
    async with AsyncOpenSearch(hosts=[_opensearch_url]) as client_:
        stored = await client_.get(index="kith-chunks", id=str(chunk.id))
    assert stored["_source"] == {
        "tenant_id": str(caller.tenant_id),
        "document_id": str(document_id),
        "page_number": 1,
        "ordinal": 0,
        "text": chunk.text,
    }


async def test_after_indexing_the_document_waits_at_embedding_with_chunks_indexed(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, make_text_pdf(["Known page text."])
    )

    db_session.expire_all()
    document = (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()
    chunks = (
        (await db_session.execute(select(Chunk).where(Chunk.document_id == document_id)))
        .scalars()
        .all()
    )
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.EMBEDDING
    assert chunks
    assert all(chunk.indexing_status == ChunkStatus.DONE for chunk in chunks)
    assert all(chunk.embedding_status == ChunkStatus.PENDING for chunk in chunks)


async def test_a_retry_leaves_no_duplicate_or_stale_chunks_in_the_index(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    search_index: SearchIndex,
) -> None:
    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, make_text_pdf(["Known page text."])
    )
    document = (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()
    document.ingestion_status = IngestionStatus.UPLOADED
    document.ingestion_stage = None
    await db_session.commit()

    await _ingest(ingest_ctx, caller, document_id)

    hits = await _search(db_session, search_index, caller, "known")
    current_ids = {
        chunk.id
        for chunk in (
            await db_session.execute(
                select(Chunk).where(Chunk.document_id == document_id)
            )
        ).scalars()
    }
    assert {hit.chunk_id for hit in hits} == current_ids
    assert len(hits) == len(current_ids)


async def test_a_deleted_documents_chunks_are_not_returned_though_still_indexed(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    search_index: SearchIndex,
) -> None:
    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, make_text_pdf(["Known page text."])
    )
    assert await _search(db_session, search_index, caller, "known")

    response = await client.delete(f"/api/v1/documents/{document_id}")
    assert response.status_code == 204

    assert await _search(db_session, search_index, caller, "known") == []


async def test_search_never_returns_another_tenants_chunks(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    search_index: SearchIndex,
) -> None:
    await _upload_and_ingest(
        client, storage, caller, ingest_ctx, make_text_pdf(["Known page text."])
    )
    other_tenant = Caller(uuid.uuid4(), caller.user_id)

    assert await _search(db_session, search_index, other_tenant, "known") == []


async def test_the_query_is_cleaned_like_the_chunks_were(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    search_index: SearchIndex,
) -> None:
    await _upload_and_ingest(
        client, storage, caller, ingest_ctx, make_text_pdf(["The final contract."])
    )

    assert await _search(db_session, search_index, caller, "  \ufb01nal  ")
    assert await _search(db_session, search_index, caller, "con\u00adtract")
    assert await _search(db_session, search_index, caller, "   ") == []
