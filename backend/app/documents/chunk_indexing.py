"""Batched indexing of a Document's Chunks from Postgres (ADR-0011), shared by
Ingestion and by the index rebuild (ADR-0019)."""

from collections.abc import Sequence
from dataclasses import dataclass

from core.logging import setup_logger
from core.retry.handler import RetryHandler
from core.search.provider import ChunkDocument, SearchIndex
from documents.config import IngestionSettings
from documents.ingestion_status import set_status_after_indexing
from documents.models import Chunk, ChunkDeadLetter, Document, IngestionStage
from documents.repository import DocumentsRepository
from documents.search_calls import SearchFailure, call_search

logger = setup_logger(__name__)


@dataclass(frozen=True)
class IndexingResult:
    indexed: int
    dead_lettered: int
    """Chunks recorded in a Chunk Dead Letter instead of indexed."""


async def index_document_chunks(
    repository: DocumentsRepository,
    document: Document,
    search_index: SearchIndex,
    retry_handler: RetryHandler,
    settings: IngestionSettings,
) -> IndexingResult:
    """Bulk-indexes the Document's Chunks in batches after the Postgres
    commit, under the Chunk rows' ids, replacing whatever an earlier attempt
    left in the index (ADR-0011).

    A batch the search store still refuses after the retries, or rejects
    outright, is recorded, not raised: its Chunks are marked `failed` and a dead-letter row is written,
    so the queue's own retry does not pile on top. The Document is then
    `partial` if any Chunk was indexed and `failed` if none was. Otherwise it
    waits at `embedding`: keyword-searchable, not ready."""
    chunks = list(await repository.list_chunks(document.id))
    # End the read's transaction before the search calls, which can take
    # minutes to fail: Postgres `now()` is the transaction's start, so the
    # `updated_at` and `created_at` written after them would be that stale.
    await repository.session.commit()
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
    return IndexingResult(
        indexed=indexed_count, dead_lettered=len(chunks) - indexed_count
    )
