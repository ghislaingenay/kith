"""The `ingest_document` job (ADR-0005): the job `finalize_upload` already
enqueues onto the `ingest` queue by this exact name, keyed by the Document's
id. This is scaffolding (issue #39) — it proves the queue/function/job-id
wiring reaches a running worker and guards against acting on a stale
Document, but does no real extraction. #40 fills in the real per-page work
behind this same signature; marking the Document `processing`/`extracting`
here is only proof the job ran, not a claim about extraction outcome."""

import uuid

from core.logging import setup_logger
from documents.exceptions import DocumentNotFoundError
from documents.models import IngestionStage, IngestionStatus
from documents.repository import DocumentsRepository

logger = setup_logger(__name__)


async def ingest_document(ctx: dict, *, document_id: str, tenant_id: str) -> None:
    session_factory = ctx["db_session_factory"]
    async with session_factory() as session:
        repository = DocumentsRepository(session)
        try:
            document = await repository.get_document(uuid.UUID(document_id))
        except DocumentNotFoundError:
            # A stale job for a Document that no longer exists.
            logger.warning(
                "ingest_document_missing", document_id=document_id, tenant_id=tenant_id
            )
            return

        if str(document.tenant_id) != tenant_id:
            logger.warning(
                "ingest_document_tenant_mismatch",
                document_id=document_id,
                tenant_id=tenant_id,
                document_tenant_id=str(document.tenant_id),
            )
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
