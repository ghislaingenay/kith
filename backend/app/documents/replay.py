"""Replay of failed indexing batches (ADR-0011).

Each open `indexing` Chunk Dead Letter is redone from the Chunk text stored
in Postgres: never from the PDF, storage, extraction or chunking. Run with
`make search-replay` (see `docs/search-quickstart.md`)."""

import argparse
import asyncio
import uuid
from dataclasses import dataclass

from core.container import container
from core.logging import setup_logger
from core.retry.handler import RetryHandler
from core.search.provider import ChunkDocument, SearchIndex
from documents.indexing_outcome import apply_indexing_outcome
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
    retry_handler: RetryHandler,
    *,
    document_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> ReplayResult:
    """Replays the open indexing rows, oldest first, optionally only one
    Document's and at most `limit` of them. Each row is its own transaction,
    so a row that fails again does not hold up the rest."""
    async with session_factory() as session:
        row_ids = [
            row.id
            for row in await DocumentsRepository(session).list_open_chunk_dead_letters(
                stage=IngestionStage.INDEXING, document_id=document_id, limit=limit
            )
        ]

    resolved = 0
    for row_id in row_ids:
        async with session_factory() as session:
            repository = DocumentsRepository(session)
            row = await repository.get_chunk_dead_letter(row_id)
            if row is None or row.status != ChunkDeadLetterStatus.OPEN:
                continue
            if await _replay_row(repository, row, search_index, retry_handler):
                resolved += 1
    return ReplayResult(resolved=resolved, failed=len(row_ids) - resolved)


async def _replay_row(
    repository: DocumentsRepository,
    row: ChunkDeadLetter,
    search_index: SearchIndex,
    retry_handler: RetryHandler,
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
            row.error = failure.error
            # A replay is an attempt even when the breaker refused the call.
            row.attempts += max(failure.attempts, 1)
            await session.commit()
            logger.warning(
                "replay_index_batch_failed",
                document_id=str(row.document_id),
                chunks=len(chunks),
                error=failure.error,
            )
            return False
        await repository.mark_chunks_indexed([chunk.id for chunk in chunks])

    row.status = ChunkDeadLetterStatus.RESOLVED
    row.resolved_at = func.now()
    if chunks and document.ingestion_status in (
        IngestionStatus.PARTIAL,
        IngestionStatus.FAILED,
    ):
        all_chunks = await repository.list_chunks(document.id)
        apply_indexing_outcome(
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
    return True


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--document-id", type=uuid.UUID, help="only this Document")
    parser.add_argument("--limit", type=int, help="at most this many rows")
    args = parser.parse_args()

    container.logging_configured()
    search_index = container.search_index()
    try:
        result = await replay_failed_batches(
            container.db_session_factory(),
            search_index,
            container.retry_handler(),
            document_id=args.document_id,
            limit=args.limit,
        )
    finally:
        await search_index.close()
        await container.db_engine().dispose()
    print(f"Replay: {result.resolved} resolved, {result.failed} still open")


if __name__ == "__main__":
    asyncio.run(main())
