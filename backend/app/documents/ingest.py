"""The `ingest_document` job (ADR-0005): the job `finalize_upload` already
enqueues onto the `ingest` queue by this exact name, keyed by the Document's
id. #39 proved the queue/function/job-id wiring and the stale-Document
guard; this fills in the real per-page extraction behind that same
signature (#40).

A page's extraction only counts as failed when the extraction call itself
raises (ADR-0010): one bad page never stops the rest, and never raises out
of this job by itself. Whether the *Document* as a whole then succeeds is
decided by the success-ratio threshold (#41): below it the Document ends
`failed` with a reason, handled inside the job and never raised, so the
queue's automatic retry only ever fires for infrastructure errors."""

import asyncio
import hashlib
import tempfile
import uuid
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pypdfium2
from core.jobs.provider import JobQueue
from core.logging import setup_logger
from core.retry.handler import RetryHandler
from core.search.provider import ChunkDocument, SearchIndex
from core.storage.provider import StorageProvider
from documents.chunker import CHUNK_TOKENIZER, chunk_page
from documents.config import IngestionSettings
from documents.ingestion_status import (
    is_ready_for_embedding,
    set_status_after_indexing,
)
from documents.job_documents import load_document_for_job
from documents.models import (
    Chunk,
    ChunkDeadLetter,
    Document,
    DocumentPage,
    ExtractionMethod,
    IngestionStage,
    IngestionStatus,
)
from documents.pdf import extract_page_text, open_pdf
from documents.repository import DocumentsRepository
from documents.search_calls import SearchFailure, call_search
from documents.text_cleaner import CLEANER_VERSION, clean_text
from sqlalchemy.ext.asyncio import AsyncSession

logger = setup_logger(__name__)

_PAGES_EXTRACTED_BATCH_SIZE = 5

_INGEST_QUEUE = "ingest"
_EMBED_FUNCTION = "embed_document"

# PDFium objects are thread-affine (pypdfium2/PDFium isn't thread-safe);
# `asyncio.to_thread` can hop across the default pool's threads between
# calls, so every PDFium call instead runs on this one pinned thread.
_PDFIUM_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="pdfium")


async def _run_in_pdfium_thread[T](func: Callable[..., T], *args: object) -> T:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_PDFIUM_EXECUTOR, func, *args)


async def ingest_document(ctx: dict, *, document_id: str, tenant_id: str) -> None:
    session_factory = ctx["db_session_factory"]
    storage: StorageProvider = ctx["storage_provider"]
    settings: IngestionSettings = ctx["ingestion_settings"]
    search_index: SearchIndex = ctx["search_index"]
    retry_handler: RetryHandler = ctx["retry_handler"]
    job_queue: JobQueue = ctx["job_queue"]
    async with session_factory() as session:
        repository = DocumentsRepository(session)
        document = await load_document_for_job(
            repository,
            job="ingest_document",
            document_id=document_id,
            tenant_id=tenant_id,
        )
        if document is None:
            return

        if document.ingestion_status != IngestionStatus.UPLOADED:
            # Per ADR-0005: check the Document's current state before acting,
            # so a stale or duplicate job doesn't redo (or clobber) work
            # another run already did.
            logger.info(
                "ingest_document_skipped",
                document_id=document_id,
                ingestion_status=document.ingestion_status,
            )
            return

        document.ingestion_status = IngestionStatus.PROCESSING
        document.ingestion_stage = IngestionStage.EXTRACTING
        await session.commit()
        logger.info("ingest_document_started", document_id=document_id)

        try:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "document.pdf"
                await _download_to(storage, document.storage_key, path)
                successful_pages, total_pages = await _extract_pages(
                    repository, document, path
                )
        except Exception:
            # Infra-level failure (page-level ones are already caught in
            # `_extract_one_page`): log for correlation, then re-raise so
            # the queue's automatic retry still fires (ADR-0010).
            logger.exception(
                "ingest_document_extraction_failed", document_id=document_id
            )
            await _reset_to_uploaded(session, document)
            raise

        if total_pages and (
            successful_pages / total_pages < settings.min_extraction_success_ratio
        ):
            # Business-level failure: recorded on the Document, never raised
            # (ADR-0010) — a static file would fail identically on retry.
            document.ingestion_status = IngestionStatus.FAILED
            document.ingestion_error = (
                f"Only {successful_pages} of {total_pages} pages could be "
                f"extracted; at least "
                f"{settings.min_extraction_success_ratio:.0%} is required."
            )
            await session.commit()
            logger.warning(
                "ingest_document_below_success_ratio",
                document_id=document_id,
                successful_pages=successful_pages,
                total_pages=total_pages,
            )
            return

        document.ingestion_stage = IngestionStage.CHUNKING
        await session.commit()
        logger.info(
            "ingest_document_extracted",
            document_id=document_id,
            pages_extracted=document.pages_extracted,
        )

        try:
            chunk_count = await _chunk_pages(repository, document, settings)
        except Exception:
            # Same rule as extraction: an infrastructure error goes back to
            # `uploaded` and re-raises so the queue's retry fires.
            logger.exception("ingest_document_chunking_failed", document_id=document_id)
            await session.rollback()
            await _reset_to_uploaded(session, document)
            raise

        if chunk_count == 0:
            document.ingestion_status = IngestionStatus.FAILED
            document.ingestion_error = (
                "No extractable text was found in this document. "
                "It may be a scanned PDF."
            )
            await session.commit()
            logger.warning("ingest_document_no_chunks", document_id=document_id)
            return
        logger.info(
            "ingest_document_chunked", document_id=document_id, chunks=chunk_count
        )

        document.ingestion_stage = IngestionStage.INDEXING
        await session.commit()
        try:
            await _index_chunks(
                repository, document, search_index, retry_handler, settings
            )
        except Exception:
            # A search store that is down or rejects a batch is recorded
            # inside `_index_chunks` and never gets here; this is storage or
            # the database failing, an infrastructure error like the others:
            # back to `uploaded`, re-raise for the retry.
            logger.exception("ingest_document_indexing_failed", document_id=document_id)
            await session.rollback()
            await _reset_to_uploaded(session, document)
            raise
        logger.info(
            "ingest_document_indexed",
            document_id=document_id,
            ingestion_status=document.ingestion_status,
        )

        if is_ready_for_embedding(document):
            await job_queue.enqueue(
                _INGEST_QUEUE,
                _EMBED_FUNCTION,
                {"document_id": document_id, "tenant_id": tenant_id},
                job_id=f"embed:{document_id}",
            )


async def _index_chunks(
    repository: DocumentsRepository,
    document: Document,
    search_index: SearchIndex,
    retry_handler: RetryHandler,
    settings: IngestionSettings,
) -> None:
    """Bulk-indexes the Document's Chunks in batches after the Postgres
    commit, under the Chunk rows' ids, replacing whatever an earlier attempt
    left in the index (ADR-0011).

    A batch the search store still refuses after the retries, or rejects
    outright, is recorded, not raised: its Chunks are marked `failed` and a dead-letter row is written,
    so the queue's own retry does not pile on top. The Document is then
    `partial` if any Chunk was indexed and `failed` if none was. Otherwise it
    waits at `embedding`: keyword-searchable, not ready."""
    chunks = list(await repository.list_chunks(document.id))
    indexed_count = 0

    async def record_failure(batch: Sequence[Chunk], failure: SearchFailure) -> None:
        chunk_ids = [chunk.id for chunk in batch]
        await repository.mark_chunks_indexing_failed(chunk_ids, error=failure.error)
        await repository.add_chunk_dead_letter(
            ChunkDeadLetter(
                tenant_id=document.tenant_id,
                document_id=document.id,
                stage=IngestionStage.INDEXING,
                chunk_ids=chunk_ids,
                error=failure.error,
                attempts=failure.attempts,
            )
        )
        await repository.session.commit()
        logger.warning(
            "ingest_document_index_batch_failed",
            document_id=str(document.id),
            chunks=len(chunk_ids),
            attempts=failure.attempts,
            error=failure.error,
        )

    delete_failure = await call_search(
        retry_handler,
        lambda: search_index.delete_document_chunks(
            tenant_id=document.tenant_id, document_id=document.id
        ),
    )
    if delete_failure is not None:
        # Stale Chunks from an earlier attempt may still be in the index, so
        # nothing is indexed on top of them.
        await record_failure(chunks, delete_failure)
    else:
        for start in range(0, len(chunks), settings.index_batch_size):
            batch = chunks[start : start + settings.index_batch_size]
            index_documents = [
                ChunkDocument(
                    id=chunk.id,
                    tenant_id=chunk.tenant_id,
                    document_id=chunk.document_id,
                    page_number=chunk.page_number,
                    ordinal=chunk.ordinal,
                    text=chunk.text,
                )
                for chunk in batch
            ]
            failure = await call_search(
                retry_handler,
                lambda index_documents=index_documents: search_index.index_chunks(
                    index_documents
                ),
            )
            if failure is not None:
                await record_failure(batch, failure)
                continue
            await repository.mark_chunks_indexed([chunk.id for chunk in batch])
            await repository.session.commit()
            indexed_count += len(batch)

    set_status_after_indexing(document, indexed=indexed_count, total=len(chunks))
    await repository.session.commit()


async def _chunk_pages(
    repository: DocumentsRepository,
    document: Document,
    settings: IngestionSettings,
) -> int:
    """Cuts every page's Clean Text into Chunks and swaps them in for the
    Document's current ones in one transaction (ADR-0011). Returns how many
    Chunks the Document now has."""
    pages = await repository.list_pages_with_clean_text(document.id)
    chunks: list[Chunk] = []
    for page in pages:
        drafts = await asyncio.to_thread(
            chunk_page,
            page.clean_text,
            size=settings.chunk_size_tokens,
            overlap=settings.chunk_overlap_tokens,
        )
        for draft in drafts:
            chunks.append(
                Chunk(
                    id=uuid.uuid4(),
                    document_id=document.id,
                    tenant_id=document.tenant_id,
                    page_number=page.page_number,
                    ordinal=len(chunks),
                    char_start=draft.char_start,
                    char_end=draft.char_end,
                    text=draft.text,
                    text_hash=hashlib.sha256(draft.text.encode()).hexdigest(),
                    token_count=draft.token_count,
                )
            )
    metadata = {
        "chunk_size": settings.chunk_size_tokens,
        "chunk_overlap": settings.chunk_overlap_tokens,
        "cleaner_version": CLEANER_VERSION,
        "tokenizer": CHUNK_TOKENIZER,
        "chunked_at": datetime.now(UTC).isoformat(),
    }
    await repository.replace_chunks(document, chunks, metadata)
    await repository.session.commit()
    return len(chunks)


async def _reset_to_uploaded(session: AsyncSession, document: Document) -> None:
    document.ingestion_status = IngestionStatus.UPLOADED
    document.ingestion_stage = None
    document.pages_extracted = None
    await session.commit()


async def _download_to(storage: StorageProvider, key: str, path: Path) -> None:
    """ PDFium can't read a stream. It needs random access to the whole PDF file."""
    file = await asyncio.to_thread(path.open, "wb")
    try:
        async for chunk in storage.download(key):
            await asyncio.to_thread(file.write, chunk)
    finally:
        await asyncio.to_thread(file.close)


async def _extract_pages(
    repository: DocumentsRepository,
    document: Document,
    path: Path,
) -> tuple[int, int]:
    """Returns `(successful_pages, total_pages)`.

    Extracts every page's text, writing one `document_pages` row per
    page. `document.pages_extracted` is written in batches of 5 pages, not
    after every page, since it's a progress counter a caller polls rather
    than reads live.

    Every PDFium call runs off the event loop via the single dedicated
    `_PDFIUM_EXECUTOR` thread — a thread, not the `ProcessPoolExecutor`
    ADR-0005 calls for. That process-pool architecture is deliberately
    deferred, not forgotten: there's nothing else CPU-bound to share a
    pool with yet."""
    pdf = await _run_in_pdfium_thread(open_pdf, path)
    try:
        total_pages = await _run_in_pdfium_thread(len, pdf)
        batch: list[DocumentPage] = []
        successful_pages = 0
        for page_number in range(1, total_pages + 1):
            page = await _extract_one_page(document, pdf, page_number)
            batch.append(page)
            if page.extraction_method != ExtractionMethod.EXTRACTION_ERROR:
                successful_pages += 1

            is_batch_full = len(batch) >= _PAGES_EXTRACTED_BATCH_SIZE
            is_last_page = page_number == total_pages
            if is_batch_full or is_last_page:
                await repository.upsert_document_pages(batch)
                document.pages_extracted = page_number
                await repository.session.commit()
                batch = []
        return successful_pages, total_pages
    finally:
        await _run_in_pdfium_thread(pdf.close)


async def _extract_one_page(
    document: Document, pdf: pypdfium2.PdfDocument, page_number: int
) -> DocumentPage:
    try:
        text = await _run_in_pdfium_thread(extract_page_text, pdf, page_number)
    except Exception as exc:  # noqa: BLE001 -- a page's extraction call raising
        # is, by definition (ADR-0010), the only thing that counts as a
        # page-level failure; it's caught here, never re-raised, so it
        # never stops the pages after it or fails the job.
        logger.warning(
            "ingest_document_page_failed",
            document_id=str(document.id),
            page_number=page_number,
            error=str(exc),
        )
        return DocumentPage(
            id=uuid.uuid4(),
            document_id=document.id,
            tenant_id=document.tenant_id,
            page_number=page_number,
            text=None,
            clean_text=None,
            extraction_method=ExtractionMethod.EXTRACTION_ERROR,
            error_detail=str(exc),
        )
    else:
        return DocumentPage(
            id=uuid.uuid4(),
            document_id=document.id,
            tenant_id=document.tenant_id,
            page_number=page_number,
            text=text,
            clean_text=clean_text(text),
            extraction_method=ExtractionMethod.TEXT_LAYER,
            error_detail=None,
        )
