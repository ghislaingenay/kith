"""Loading the Document an ingestion job was queued for."""

import uuid

from core.logging import setup_logger
from documents.exceptions import DocumentNotFoundError
from documents.models import Document
from documents.repository import DocumentsRepository

logger = setup_logger(__name__)


async def load_document_for_job(
    repository: DocumentsRepository, *, job: str, document_id: str, tenant_id: str
) -> Document | None:
    """The Document, or `None` (logged as `{job}_missing` or
    `{job}_tenant_mismatch`) when a stale job names one that no longer exists
    or that belongs to another Tenant."""
    try:
        document = await repository.get_document(uuid.UUID(document_id))
    except DocumentNotFoundError:
        logger.warning(f"{job}_missing", document_id=document_id, tenant_id=tenant_id)
        return None
    if str(document.tenant_id) != tenant_id:
        logger.warning(
            f"{job}_tenant_mismatch",
            document_id=document_id,
            tenant_id=tenant_id,
            document_tenant_id=str(document.tenant_id),
        )
        return None
    return document
