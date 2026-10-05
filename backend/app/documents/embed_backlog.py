"""Enqueues `embed_document` for Documents waiting at `embedding` or `partial`,
such as those ingested before the embedding phase (ADR-0014). It only enqueues: the
worker does the embedding, under its retries and breaker, so this takes no
embedding provider. The command that runs it is `scripts/embed_documents.py`
(see `docs/search-quickstart.md`)."""

import uuid

from core.jobs.provider import JobQueue
from documents.embed_jobs import enqueue_embed_document
from documents.repository import DocumentsRepository
from sqlalchemy.ext.asyncio import async_sessionmaker


async def enqueue_embedding_backlog(
    session_factory: async_sessionmaker,
    job_queue: JobQueue,
    *,
    document_id: uuid.UUID | None = None,
) -> int:
    """Returns how many Documents it handed to the queue. Running it again
    queues nothing twice (a job id already queued is skipped), and the job
    itself embeds only Chunks still pending."""
    async with session_factory() as session:
        documents = await DocumentsRepository(
            session
        ).list_documents_waiting_for_embedding(document_id=document_id)
    for document in documents:
        await enqueue_embed_document(
            job_queue, document_id=document.id, tenant_id=document.tenant_id
        )
    return len(documents)
