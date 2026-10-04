"""What indexing leaves a Document as (ADR-0011), whether it was the first
attempt or a replay of failed batches."""

from documents.models import Document, IngestionStage, IngestionStatus


def apply_indexing_outcome(document: Document, *, indexed: int, total: int) -> None:
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
