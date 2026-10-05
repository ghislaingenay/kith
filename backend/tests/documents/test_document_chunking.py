"""Tests for #49: each page's Clean Text is cut into stored Chunks by
`ingest_document`, through the same seam as the extraction tests: real PDFs,
`FakeStorageProvider`, and the real Postgres test database."""

import hashlib
import uuid
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from core.search.provider import SearchIndex
from core.database import DatabaseSettings, create_engine, create_session_factory
from documents.config import IngestionSettings
from documents.ingest import ingest_document
from documents.keys import pending_upload_key
from documents.chunker import CHUNK_TOKENIZER
from documents.models import (
    Chunk,
    ChunkStatus,
    Document,
    DocumentPage,
    IngestionStage,
    IngestionStatus,
)
from fpdf import FPDF
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents.conftest import (
    Caller,
    fast_retry_handler,
    finalize_upload,
    init_upload,
    make_text_pdf,
)
from tests.support.fake_job_queue import FakeJobQueue
from tests.support.fake_storage import FakeStorageProvider

_FRENCH = (
    "Le présent contrat est conclu entre les parties pour une durée de douze "
    "mois, renouvelable par tacite reconduction sauf dénonciation écrite. "
    "Chaque partie s'engage à exécuter ses obligations de bonne foi. "
)
_ENGLISH = (
    "This agreement is entered into by the parties for a term of twelve "
    "months, renewable automatically unless terminated in writing. Each "
    "party agrees to perform its obligations in good faith. "
)


def make_prose_pdf(pages: list[str]) -> bytes:
    """One page per string, wrapped over many lines like real prose."""
    pdf = FPDF()
    for text in pages:
        pdf.add_page()
        pdf.set_font("helvetica", size=8)
        pdf.multi_cell(w=0, h=4, text=text)
    return bytes(pdf.output())


def _prose(sentence: str, repeats: int) -> str:
    return (sentence * repeats).strip()


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
        "retry_handler": fast_retry_handler(),
        "job_queue": FakeJobQueue(),
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


async def _chunks_of(db_session: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
    db_session.expire_all()
    result = await db_session.execute(
        select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.ordinal)
    )
    return list(result.scalars())


async def _pages_by_number(
    db_session: AsyncSession, document_id: uuid.UUID
) -> dict[int, DocumentPage]:
    result = await db_session.execute(
        select(DocumentPage).where(DocumentPage.document_id == document_id)
    )
    return {page.page_number: page for page in result.scalars()}


async def _document(db_session: AsyncSession, document_id: uuid.UUID) -> Document:
    db_session.expire_all()
    return (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()


async def test_a_multi_page_pdf_yields_page_bounded_chunks_with_full_records(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf = make_prose_pdf([_prose(_FRENCH, 14), _prose(_ENGLISH, 14)])

    document_id = await _upload_and_ingest(client, storage, caller, ingest_ctx, pdf)

    chunks = await _chunks_of(db_session, document_id)
    pages = await _pages_by_number(db_session, document_id)
    assert {chunk.page_number for chunk in chunks} == {1, 2}
    assert [chunk.ordinal for chunk in chunks] == list(range(len(chunks)))
    assert [chunk.page_number for chunk in chunks] == sorted(
        chunk.page_number for chunk in chunks
    )
    for chunk in chunks:
        clean = pages[chunk.page_number].clean_text
        assert clean[chunk.char_start : chunk.char_end] == chunk.text
        assert chunk.text_hash == hashlib.sha256(chunk.text.encode()).hexdigest()
        assert chunk.token_count > 0
        assert chunk.tenant_id == caller.tenant_id
        assert chunk.indexing_status == ChunkStatus.DONE
        assert chunk.embedding_status == ChunkStatus.PENDING
    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.EMBEDDING


@pytest.mark.parametrize("sentence", [_FRENCH, _ENGLISH], ids=["french", "english"])
async def test_chunk_sizes_stay_close_to_the_500_token_target(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    sentence: str,
) -> None:
    pdf = make_prose_pdf([_prose(sentence, 40)])

    document_id = await _upload_and_ingest(client, storage, caller, ingest_ctx, pdf)

    chunks = await _chunks_of(db_session, document_id)
    assert len(chunks) >= 3
    assert all(chunk.token_count <= 500 for chunk in chunks)
    assert all(chunk.token_count >= 400 for chunk in chunks[:-1])


async def test_the_chunking_record_holds_how_the_chunks_were_made(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf = make_text_pdf(["Hello, known text."])

    document_id = await _upload_and_ingest(client, storage, caller, ingest_ctx, pdf)

    record = (await _document(db_session, document_id)).chunk_metadata
    assert record is not None
    assert record["chunk_size"] == 500
    assert record["chunk_overlap"] == 50
    assert record["cleaner_version"] == 1
    assert record["tokenizer"] == CHUNK_TOKENIZER
    assert record["chunked_at"]


async def test_size_and_overlap_are_configurable(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    ingest_ctx["ingestion_settings"] = IngestionSettings.model_validate(
        {"INGESTION_CHUNK_SIZE_TOKENS": 60, "INGESTION_CHUNK_OVERLAP_TOKENS": 5}
    )
    pdf = make_prose_pdf([_prose(_ENGLISH, 6)])

    document_id = await _upload_and_ingest(client, storage, caller, ingest_ctx, pdf)

    chunks = await _chunks_of(db_session, document_id)
    assert len(chunks) > 3
    assert all(chunk.token_count <= 60 for chunk in chunks)
    record = (await _document(db_session, document_id)).chunk_metadata
    assert (record["chunk_size"], record["chunk_overlap"]) == (60, 5)


def test_overlap_must_be_smaller_than_size() -> None:
    with pytest.raises(ValidationError):
        IngestionSettings.model_validate(
            {"INGESTION_CHUNK_SIZE_TOKENS": 50, "INGESTION_CHUNK_OVERLAP_TOKENS": 50}
        )


async def test_blank_pages_produce_no_chunks_but_text_pages_still_do(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf = make_text_pdf(["First page text.", "", "Third page text."])

    document_id = await _upload_and_ingest(client, storage, caller, ingest_ctx, pdf)

    chunks = await _chunks_of(db_session, document_id)
    assert [chunk.page_number for chunk in chunks] == [1, 3]
    assert [chunk.ordinal for chunk in chunks] == [0, 1]


async def test_a_document_with_no_chunks_ends_failed_with_a_readable_reason(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf = make_text_pdf(["", ""])

    document_id = await _upload_and_ingest(client, storage, caller, ingest_ctx, pdf)

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.FAILED
    assert "no extractable text" in document.ingestion_error.lower()
    assert "scanned" in document.ingestion_error.lower()
    assert await _chunks_of(db_session, document_id) == []


async def test_a_forced_offset_mismatch_stores_unknown_offsets_and_warns(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class _Splitter:
        def split_text(self, text: str) -> list[str]:
            return [text, "text the page never contained"]

    with patch("documents.chunker._splitter", return_value=_Splitter()):
        document_id = await _upload_and_ingest(
            client, storage, caller, ingest_ctx, make_text_pdf(["Known page text."])
        )

    matching, mismatched = await _chunks_of(db_session, document_id)
    assert (matching.char_start, matching.char_end) == (0, 16)
    assert (mismatched.char_start, mismatched.char_end) == (None, None)
    assert "chunk_offsets_mismatch" in capsys.readouterr().out


async def test_a_retry_replaces_chunks_and_the_record_without_stale_rows(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf = make_prose_pdf([_prose(_ENGLISH, 14), _prose(_FRENCH, 14)])
    document_id = await _upload_and_ingest(client, storage, caller, ingest_ctx, pdf)
    first = await _chunks_of(db_session, document_id)
    first_ids = {chunk.id for chunk in first}
    first_texts = [chunk.text for chunk in first]
    db_session.add(
        Chunk(
            document_id=document_id,
            tenant_id=caller.tenant_id,
            page_number=9,
            ordinal=999,
            text="stale",
            text_hash="x",
            token_count=1,
        )
    )
    document = await _document(db_session, document_id)
    document.chunk_metadata = {"chunk_size": 1}
    document.ingestion_status = IngestionStatus.UPLOADED
    document.ingestion_stage = None
    await db_session.commit()

    await _ingest(ingest_ctx, caller, document_id)

    second = await _chunks_of(db_session, document_id)
    assert [chunk.text for chunk in second] == first_texts
    assert [chunk.ordinal for chunk in second] == list(range(len(first_texts)))
    assert not first_ids & {chunk.id for chunk in second}
    assert (await _document(db_session, document_id)).chunk_metadata[
        "chunk_size"
    ] == 500
