"""Tests for #40's real `ingest_document` extraction: one `document_pages`
row per page, written through the seam this feature's tests run through —
`ingest_document` called directly (not through a real arq worker, that's
already proven by test_ingest_worker.py), `StorageProvider` swapped for
`FakeStorageProvider`, and the real Postgres test database — matching the
existing upload feature's test convention in this domain."""

import uuid
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.storage.dependencies import get_storage_provider
from core.storage.exceptions import StorageError
from documents.ingest import ingest_document
from documents.keys import pending_upload_key
from documents.models import (
    Document,
    DocumentPage,
    ExtractionMethod,
    IngestionStage,
    IngestionStatus,
)
from documents.repository import DocumentsRepository
from httpx import AsyncClient
from main import app
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents.conftest import (
    Caller,
    finalize_upload,
    init_upload,
    make_image_only_pdf,
    make_rotated_text_pdf,
    make_text_pdf,
    make_two_column_pdf,
)
from tests.support.fake_storage import FakeStorageProvider

_ACCENTED_TEXT = "Café résumé naïve façade"


@pytest.fixture
async def ingest_ctx(
    _database_url: str, storage: FakeStorageProvider
) -> AsyncIterator[dict]:
    """A `ctx` dict shaped the way the worker builds one at startup
    (`workers/ingest.py`): a real `db_session_factory` against the same
    Postgres `db_session` uses, and `StorageProvider` swapped for the
    `FakeStorageProvider` this domain's other upload tests already fake."""
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield {
        "db_session_factory": create_session_factory(engine),
        "storage_provider": storage,
    }
    await engine.dispose()


async def _upload_and_finalize(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    pdf_bytes: bytes,
) -> uuid.UUID:
    upload_id = (await init_upload(client, pdf_bytes)).json()["upload_id"]
    storage.put_object(
        pending_upload_key(caller.tenant_id, uuid.UUID(upload_id)), pdf_bytes
    )
    document_id = (await finalize_upload(client, upload_id)).json()["id"]
    return uuid.UUID(document_id)


async def _ingest(ctx: dict, caller: Caller, document_id: uuid.UUID) -> None:
    await ingest_document(
        ctx, document_id=str(document_id), tenant_id=str(caller.tenant_id)
    )


async def _upload_and_ingest(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    ctx: dict,
    pdf_bytes: bytes,
) -> uuid.UUID:
    document_id = await _upload_and_finalize(client, storage, caller, pdf_bytes)
    await _ingest(ctx, caller, document_id)
    return document_id


async def _pages_of(
    db_session: AsyncSession, document_id: uuid.UUID
) -> list[DocumentPage]:
    result = await db_session.execute(
        select(DocumentPage)
        .where(DocumentPage.document_id == document_id)
        .order_by(DocumentPage.page_number)
    )
    return list(result.scalars())


async def _document(db_session: AsyncSession, document_id: uuid.UUID) -> Document:
    result = await db_session.execute(
        select(Document).where(Document.id == document_id)
    )
    return result.scalar_one()


async def test_a_single_page_with_known_text_is_extracted(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf_bytes = make_text_pdf(["Hello, known text."])

    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, pdf_bytes
    )

    [page] = await _pages_of(db_session, document_id)
    assert page.page_number == 1
    assert page.text == "Hello, known text."
    assert page.extraction_method == ExtractionMethod.TEXT_LAYER
    assert page.error_detail is None
    assert page.tenant_id == caller.tenant_id


async def test_a_multi_page_document_extracts_every_page_in_order(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    texts = ["Page one text.", "Page two text.", "Page three text."]
    pdf_bytes = make_text_pdf(texts)

    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, pdf_bytes
    )

    pages = await _pages_of(db_session, document_id)
    assert [page.page_number for page in pages] == [1, 2, 3]
    assert [page.text for page in pages] == texts
    assert all(page.extraction_method == ExtractionMethod.TEXT_LAYER for page in pages)


async def test_a_genuinely_blank_page_extracts_as_empty_text_not_a_failure(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf_bytes = make_text_pdf([""])

    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, pdf_bytes
    )

    [page] = await _pages_of(db_session, document_id)
    assert page.text == ""
    assert page.extraction_method == ExtractionMethod.TEXT_LAYER
    assert page.error_detail is None


async def test_a_two_column_layout_extracts_text_from_both_columns(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf_bytes = make_two_column_pdf("Left column text.", "Right column text.")

    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, pdf_bytes
    )

    [page] = await _pages_of(db_session, document_id)
    assert "Left column text." in page.text
    assert "Right column text." in page.text
    assert page.extraction_method == ExtractionMethod.TEXT_LAYER


async def test_a_rotated_page_still_extracts_its_text(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf_bytes = make_rotated_text_pdf("Rotated page text.", rotation=90)

    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, pdf_bytes
    )

    [page] = await _pages_of(db_session, document_id)
    assert page.text == "Rotated page text."
    assert page.extraction_method == ExtractionMethod.TEXT_LAYER


async def test_accented_non_ascii_text_extracts_correctly(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf_bytes = make_text_pdf([_ACCENTED_TEXT])

    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, pdf_bytes
    )

    [page] = await _pages_of(db_session, document_id)
    assert page.text == _ACCENTED_TEXT


async def test_an_image_only_page_extracts_as_empty_text_not_a_failure(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf_bytes = make_image_only_pdf()

    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, pdf_bytes
    )

    [page] = await _pages_of(db_session, document_id)
    assert page.text == ""
    assert page.extraction_method == ExtractionMethod.TEXT_LAYER
    assert page.error_detail is None


async def test_one_pages_extraction_call_raising_does_not_stop_the_rest(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    texts = ["Page one.", "Page two.", "Page three."]
    document_id = await _upload_and_finalize(
        client, storage, caller, make_text_pdf(texts)
    )

    from documents.pdf import extract_page_text as real_extract_page_text

    def _raise_on_page_two(pdf, page_number):
        if page_number == 2:
            raise RuntimeError("simulated extraction failure")
        return real_extract_page_text(pdf, page_number)

    with patch("documents.ingest.extract_page_text", side_effect=_raise_on_page_two):
        await _ingest(ingest_ctx, caller, document_id)

    pages = await _pages_of(db_session, document_id)
    assert [page.extraction_method for page in pages] == [
        ExtractionMethod.TEXT_LAYER,
        ExtractionMethod.EXTRACTION_ERROR,
        ExtractionMethod.TEXT_LAYER,
    ]
    assert pages[0].text == "Page one."
    assert pages[1].text is None
    assert "simulated extraction failure" in pages[1].error_detail
    assert pages[2].text == "Page three."

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.CHUNKING
    assert document.pages_extracted == 3


async def test_pages_extracted_is_written_in_batches_of_five_not_every_page(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf_bytes = make_text_pdf([f"Page {page_number}" for page_number in range(1, 8)])
    document_id = await _upload_and_finalize(client, storage, caller, pdf_bytes)

    batch_sizes: list[int] = []
    original_upsert = DocumentsRepository.upsert_document_pages

    async def _tracking_upsert(self, pages):
        batch_sizes.append(len(pages))
        return await original_upsert(self, pages)

    with patch.object(DocumentsRepository, "upsert_document_pages", _tracking_upsert):
        await _ingest(ingest_ctx, caller, document_id)

    assert batch_sizes == [5, 2]
    document = await _document(db_session, document_id)
    assert document.pages_extracted == 7
    assert len(await _pages_of(db_session, document_id)) == 7


async def test_a_completed_run_leaves_the_document_at_processing_chunking(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    db_session: AsyncSession,
    ingest_ctx: dict,
) -> None:
    pdf_bytes = make_text_pdf(["Only page."])

    document_id = await _upload_and_ingest(
        client, storage, caller, ingest_ctx, pdf_bytes
    )

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.PROCESSING
    assert document.ingestion_stage == IngestionStage.CHUNKING
    assert document.pages_extracted == 1


class _StorageThatCannotDownloadTheDocument(FakeStorageProvider):
    """Fails only once ingestion tries to download the Document's
    permanent object — the pending-upload download that finalize itself
    performs (a different key, under `pending/`) still succeeds, so a
    Document can be created to ingest in the first place."""

    async def download(self, key):
        if key.startswith("tenants/"):
            raise StorageError("storage unavailable")
        async for chunk in super().download(key):
            yield chunk


async def test_an_infrastructure_failure_propagates_instead_of_being_swallowed(
    client: AsyncClient,
    caller: Caller,
    db_session: AsyncSession,
    _database_url: str,
) -> None:
    storage = _StorageThatCannotDownloadTheDocument()
    app.dependency_overrides[get_storage_provider] = lambda: storage
    document_id = await _upload_and_finalize(
        client, storage, caller, make_text_pdf(["Page one."])
    )
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    ctx = {
        "db_session_factory": create_session_factory(engine),
        "storage_provider": storage,
    }

    with pytest.raises(StorageError):
        await _ingest(ctx, caller, document_id)
    await engine.dispose()

    document = await _document(db_session, document_id)
    assert document.ingestion_status == IngestionStatus.UPLOADED
    assert document.ingestion_stage == None
    assert await _pages_of(db_session, document_id) == []
