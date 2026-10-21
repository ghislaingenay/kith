"""Replay of failed indexing and embedding batches (ADR-0011, ADR-0014).

Each open Chunk Dead Letter is redone from the Chunk text stored in Postgres:
never from the PDF, storage, extraction or chunking. `indexing` rows are
replayed before `embedding` ones. The command that runs it is
`scripts/replay_failed_batches.py` (see `docs/search-quickstart.md`)."""

import uuid
from dataclasses import dataclass

from core.embedding.provider import EmbeddingInputType, EmbeddingProvider
from core.jobs.provider import JobQueue
from core.logging import setup_logger
from core.retry.handler import RetryHandler
from core.search.provider import ChunkDocument, SearchIndex
from documents.embed_jobs import enqueue_embed_document
from documents.embedding_calls import EmbeddingFailure, call_embedding
from documents.exceptions import EmbeddingProviderRequiredError
from documents.ingestion_status import (
    set_status_after_embedding,
    set_status_after_indexing,
)
from documents.models import (
    ChunkDeadLetter,
    ChunkDeadLetterStatus,
    ChunkStatus,
    IngestionStage,
    IngestionStatus,
)
from documents.repository import DocumentsRepository
from documents.search_calls import call_search
from sqlalchemy import func
from sqlalchemy.ext.asyncio import async_sessionmaker

logger = setup_logger(__name__)


@dataclass(frozen=True)
class ReplayResult:
    resolved: int
    failed: int
    """Rows that failed again and stay open."""


async def replay_failed_batches(
    session_factory: async_sessionmaker,
    search_index: SearchIndex,
    embedding_provider: EmbeddingProvider | None,
    retry_handler: RetryHandler,
    job_queue: JobQueue,
    *,
    stage: IngestionStage | None = None,
    document_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> ReplayResult:
    """Replays the open rows, `indexing` before `embedding` and oldest first
    within a stage, optionally only one stage's or one Document's and at most
    `limit` of them. Each row is its own transaction, so a row that fails
    again does not hold up the rest. Only embedding rows need the
    `embedding_provider`, so an indexing-only replay can go without one. An
    indexing row that is resolved queues `embed_document` for its Document,
    so the Chunks it made searchable get vectors (ADR-0014)."""
    stages = [stage] if stage else [IngestionStage.INDEXING, IngestionStage.EMBEDDING]
    if embedding_provider is None and IngestionStage.EMBEDDING in stages:
        raise EmbeddingProviderRequiredError(
            "Replaying embedding rows needs an embedding provider"
        )
    row_ids: list[uuid.UUID] = []
    async with session_factory() as session:
        repository = DocumentsRepository(session)
        for stage_to_replay in stages:
            remaining = None if limit is None else limit - len(row_ids)
            if remaining == 0:
                break
            row_ids.extend(
                row.id
                for row in await repository.list_open_chunk_dead_letters(
                    stage=stage_to_replay, document_id=document_id, limit=remaining
                )
            )

    resolved = 0
    for row_id in row_ids:
        async with session_factory() as session:
            repository = DocumentsRepository(session)
            row = await repository.get_chunk_dead_letter(row_id)
            if row is None or row.status != ChunkDeadLetterStatus.OPEN:
                continue
            if row.stage == IngestionStage.EMBEDDING:
                assert embedding_provider is not None  # checked above
                is_resolved = await _replay_embedding_row(
                    repository, row, search_index, embedding_provider, retry_handler
                )
            else:
                is_resolved = await _replay_indexing_row(
                    repository, row, search_index, retry_handler, job_queue
                )
            if is_resolved:
                resolved += 1
    return ReplayResult(resolved=resolved, failed=len(row_ids) - resolved)


def _note_repeat_failure(row: ChunkDeadLetter, *, error: str, attempts: int) -> None:
    row.error = error
    # A replay is an attempt even when the breaker refused the call.
    row.attempts += max(attempts, 1)


def _resolve(row: ChunkDeadLetter) -> None:
    row.status = ChunkDeadLetterStatus.RESOLVED
    row.resolved_at = func.now()


async def _replay_indexing_row(
    repository: DocumentsRepository,
    row: ChunkDeadLetter,
    search_index: SearchIndex,
    retry_handler: RetryHandler,
    job_queue: JobQueue,
) -> bool:
    """Returns whether the row is resolved."""
    session = repository.session
    document = await repository.get_document(row.document_id)
    # A deleted Document's Chunks are not made searchable, and Chunks that no
    # longer exist (the Document was chunked again) have nothing to replay.
    chunks = (
        []
        if document.ingestion_status == IngestionStatus.DELETED
        else await repository.list_chunks_by_ids(row.chunk_ids)
    )
    if chunks:
        # End the read's transaction before the search call, so the timestamps
        # written after it are not the start of the call (see
        # `index_document_chunks`).
        await session.commit()
        failure = await call_search(
            retry_handler,
            lambda: search_index.index_chunks(
                [
                    ChunkDocument(
                        id=chunk.id,
                        tenant_id=chunk.tenant_id,
                        document_id=chunk.document_id,
                        page_number=chunk.page_number,
                        ordinal=chunk.ordinal,
                        text=chunk.text,
                    )
                    for chunk in chunks
                ]
            ),
        )
        if failure is not None:
            await repository.mark_chunks_indexing_failed(
                [chunk.id for chunk in chunks], error=failure.error
            )
            _note_repeat_failure(row, error=failure.error, attempts=failure.attempts)
            await session.commit()
            logger.warning(
                "replay_index_batch_failed",
                document_id=str(row.document_id),
                chunks=len(chunks),
                error=failure.error,
            )
            return False
        await repository.mark_chunks_indexed([chunk.id for chunk in chunks])

    _resolve(row)
    if chunks and document.ingestion_status in (
        IngestionStatus.PARTIAL,
        IngestionStatus.FAILED,
    ):
        all_chunks = await repository.list_chunks(document.id)
        set_status_after_indexing(
            document,
            indexed=sum(c.indexing_status == ChunkStatus.DONE for c in all_chunks),
            total=len(all_chunks),
        )
    await session.commit()
    logger.info(
        "replay_index_batch_resolved",
        document_id=str(row.document_id),
        chunks=len(chunks),
    )
    if chunks:
        # After the commit, so the job reads the Chunks as indexed. If this
        # enqueue fails, `make embed-documents` still finds the Document.
        await enqueue_embed_document(
            job_queue, document_id=document.id, tenant_id=document.tenant_id
        )
    return True


async def _replay_embedding_row(
    repository: DocumentsRepository,
    row: ChunkDeadLetter,
    search_index: SearchIndex,
    embedding_provider: EmbeddingProvider,
    retry_handler: RetryHandler,
) -> bool:
    """Returns whether the row is resolved."""
    session = repository.session
    document = await repository.get_document(row.document_id)
    # A deleted Document gets no vectors, and Chunks that no longer exist have
    # nothing to replay.
    chunks = (
        []
        if document.ingestion_status == IngestionStatus.DELETED
        else list(await repository.list_chunks_by_ids(row.chunk_ids))
    )
    chunks_not_in_index: set[uuid.UUID] = set()
    if chunks:
        result = await call_embedding(
            retry_handler,
            lambda: embedding_provider.embed(
                [chunk.text for chunk in chunks],
                input_type=EmbeddingInputType.DOCUMENT,
            ),
        )
        if isinstance(result, EmbeddingFailure):
            await repository.mark_chunks_embedding_failed(
                [chunk.id for chunk in chunks], error=result.error
            )
            _note_repeat_failure(row, error=result.error, attempts=result.attempts)
            await session.commit()
            logger.warning(
                "replay_embed_batch_failed",
                document_id=str(row.document_id),
                chunks=len(chunks),
                error=result.error,
            )
            return False
        chunks_not_in_index = set(
            await search_index.set_chunk_embeddings(
                tenant_id=document.tenant_id,
                embeddings={
                    chunk.id: vector
                    for chunk, vector in zip(chunks, result.vectors, strict=True)
                },
            )
        )
        await repository.mark_chunks_embedded(
            [chunk.id for chunk in chunks if chunk.id not in chunks_not_in_index]
        )

    _resolve(row)
    if chunks_not_in_index:
        # The Document was deleted mid-replay: there is nothing to recompute.
        logger.warning(
            "replay_embed_chunks_not_in_index",
            document_id=str(row.document_id),
            chunks=len(chunks_not_in_index),
        )
    elif chunks:
        set_status_after_embedding(document, await repository.list_chunks(document.id))
    await session.commit()
    logger.info(
        "replay_embed_batch_resolved",
        document_id=str(row.document_id),
        chunks=len(chunks),
    )
    return True
