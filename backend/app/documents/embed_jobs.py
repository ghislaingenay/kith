"""How an `embed_document` job is put on the queue (ADR-0014). Shared by
ingestion, which enqueues it once indexing finishes, and the backlog command."""

import uuid

from core.jobs.provider import JobQueue

INGEST_QUEUE = "ingest"
_EMBED_FUNCTION = "embed_document"


async def enqueue_embed_document(
    job_queue: JobQueue, *, document_id: uuid.UUID | str, tenant_id: uuid.UUID | str
) -> None:
    """Under the job id `embed:{document_id}`, so a Document already queued
    or running is not queued again."""
    await job_queue.enqueue(
        INGEST_QUEUE,
        _EMBED_FUNCTION,
        {"document_id": str(document_id), "tenant_id": str(tenant_id)},
        job_id=f"embed:{document_id}",
    )
