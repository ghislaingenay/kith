"""What indexing and embedding leave a Document as (ADR-0011, ADR-0014),
whether it was the first attempt or a replay of failed batches."""

from collections.abc import Sequence

from documents.models import (
    Chunk,
    ChunkStatus,
    Document,
    IngestionStage,
    IngestionStatus,
)


def set_status_after_indexing(document: Document, *, indexed: int, total: int) -> None:
    """All Chunks indexed: the Document waits at `embedding`, keyword-searchable
    but not ready. None: `failed`. Some: `partial`."""
    failed = total - indexed
    if failed == 0:
        document.ingestion_status = IngestionStatus.PROCESSING
        document.ingestion_stage = IngestionStage.EMBEDDING
        document.ingestion_error = None
    elif indexed == 0:
        document.ingestion_status = IngestionStatus.FAILED
        document.ingestion_error = (
            "The search service could not index this document, so none of "
            "its text could be made searchable. Please try again later."
        )
    else:
        document.ingestion_status = IngestionStatus.PARTIAL
        document.ingestion_error = (
            f"The search service could not index {failed} of "
            f"{total} passages of this document, so they could not be "
            "made searchable."
        )


def is_ready_for_embedding(document: Document) -> bool:
    """Whether embedding has work to do for the Document: it waits at
    `embedding`, or it is `partial` and its indexed Chunks still need
    vectors."""
    return document.ingestion_status == IngestionStatus.PARTIAL or (
        document.ingestion_status == IngestionStatus.PROCESSING
        and document.ingestion_stage == IngestionStage.EMBEDDING
    )


def set_status_after_embedding(document: Document, chunks: Sequence[Chunk]) -> None:
    """From both Chunk statuses. A Chunk is searchable once it is indexed and
    embedded, so one that failed either step is not. `ready` when every Chunk
    is, `failed` when none is, `partial` otherwise. Indexed Chunks still
    waiting for a vector leave the Document as it is, waiting at
    `embedding`."""
    searchable = sum(
        chunk.indexing_status == ChunkStatus.DONE
        and chunk.embedding_status == ChunkStatus.DONE
        for chunk in chunks
    )
    waiting_for_vector = any(
        chunk.indexing_status == ChunkStatus.DONE
        and chunk.embedding_status == ChunkStatus.PENDING
        for chunk in chunks
    )
    if waiting_for_vector:
        return
    total = len(chunks)
    failed = total - searchable
    if failed == 0:
        document.ingestion_status = IngestionStatus.READY
        document.ingestion_stage = IngestionStage.EMBEDDING
        document.ingestion_error = None
    elif searchable == 0:
        document.ingestion_status = IngestionStatus.FAILED
        document.ingestion_error = (
            "None of this document's text could be made searchable. "
            "Please try again later."
        )
    else:
        document.ingestion_status = IngestionStatus.PARTIAL
        document.ingestion_error = (
            f"{failed} of {total} passages of this document could not be "
            "made searchable."
        )
