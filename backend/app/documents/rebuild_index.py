"""Refills the search index from Postgres after it is lost, without extracting
the PDFs again (ADR-0019). The same command fills a fresh index on a new
cluster. The command that runs it is `scripts/rebuild_index.py` (see
`docs/search-quickstart.md`)."""

from dataclasses import dataclass

from core.jobs.provider import JobQueue
from core.retry.handler import RetryHandler
from core.search.provider import SearchIndex
from documents.chunk_indexing import index_document_chunks
from documents.config import IngestionSettings
from documents.embed_jobs import INGEST_QUEUE, enqueue_embed_document
from documents.exceptions import IngestionInProgressError
from documents.ingestion_status import is_ready_for_embedding
from documents.repository import DocumentsRepository
from sqlalchemy.ext.asyncio import async_sessionmaker


@dataclass(frozen=True)
class RebuildResult:
    documents_reindexed: int
    documents_queued_for_embedding: int
    chunks_dead_lettered: int


async def rebuild_index(
    session_factory: async_sessionmaker,
    search_index: SearchIndex,
    job_queue: JobQueue,
    retry_handler: RetryHandler,
    settings: IngestionSettings,
) -> RebuildResult:
    """Drops the index and creates it again, with its alias and search
    pipeline, then re-indexes every Document past chunking from its Chunk
    rows, as Ingestion does, dead letters included. Each one's Chunks wait
    for a vector again and its `embed_document` job is queued (ADR-0014): the
    vectors were only in the index. Documents earlier in Ingestion, failed
    with no Chunks, or deleted are left alone. Each Document is its own
    transaction, and running it again gives the same result. A Document
    deleted while it runs is skipped.

    Its open Chunk Dead Letters are closed, since every Chunk is indexed and
    embedded again; a batch that fails now gets a new row. Refuses to start
    while ingestion jobs are waiting or running, so none writes to a Document
    it rebuilds (the jobs it queues itself run behind it)."""
    jobs = await job_queue.count_jobs(INGEST_QUEUE)
    if jobs:
        raise IngestionInProgressError(
            f"{jobs} ingestion job(s) are waiting or running; "
            "wait until the queue is empty"
        )
    await search_index.recreate_index()
    async with session_factory() as session:
        documents = await DocumentsRepository(session).list_documents_past_chunking()

    reindexed = 0
    queued = 0
    dead_lettered = 0
    for listed_document in documents:
        async with session_factory() as session:
            repository = DocumentsRepository(session)
            document = await repository.get_live_document(
                tenant_id=listed_document.tenant_id, document_id=listed_document.id
            )
            if document is None:
                continue
            await repository.resolve_open_chunk_dead_letters(document.id)
            await repository.mark_document_chunks_pending_embedding(document.id)
            dead_lettered += await index_document_chunks(
                repository, document, search_index, retry_handler, settings
            )
            reindexed += 1
            if is_ready_for_embedding(document):
                # After the commit, so the job reads the Chunks as indexed.
                await enqueue_embed_document(
                    job_queue, document_id=document.id, tenant_id=document.tenant_id
                )
                queued += 1
    return RebuildResult(
        documents_reindexed=reindexed,
        documents_queued_for_embedding=queued,
        chunks_dead_lettered=dead_lettered,
    )
