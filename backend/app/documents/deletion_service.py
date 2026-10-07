"""Business logic for deleting Documents."""

import uuid

from core.circuit_breaker.exceptions import CircuitOpenError
from core.jobs.provider import JobQueue
from core.logging import setup_logger
from core.search.exceptions import SearchError
from core.search.provider import SearchIndex
from documents.exceptions import DocumentNotFoundError
from documents.repository import DocumentsRepository
from tenants.exceptions import PermissionDenied
from tenants.permissions import Action, Role, has_permission

logger = setup_logger(__name__)

_TASKS_QUEUE = "tasks"
_PURGE_FUNCTION = "purge_document"


class DocumentDeletionService:
    def __init__(
        self,
        repository: DocumentsRepository,
        job_queue: JobQueue,
        search_index: SearchIndex,
    ) -> None:
        self.repository = repository
        self.job_queue = job_queue
        self.search_index = search_index

    async def delete_document(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        role: Role,
        document_id: uuid.UUID,
    ) -> None:
        document = await self.repository.get_live_document_for_update(
            tenant_id=tenant_id, document_id=document_id
        )
        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} not found.")
        is_uploader = document.uploader_id == user_id
        if not is_uploader and not has_permission(role, Action.DELETE_ANY_DOCUMENT):
            raise PermissionDenied(Action.DELETE_ANY_DOCUMENT)
        await self.repository.mark_document_deleted(document, deleted_by=user_id)
        await self.job_queue.enqueue(
            _TASKS_QUEUE,
            _PURGE_FUNCTION,
            {"document_id": str(document_id), "tenant_id": str(tenant_id)},
            job_id=f"purge:{document_id}",
        )
        await self._hide_chunks_from_search(tenant_id, document_id)

    async def _hide_chunks_from_search(
        self, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """Flags the Document's Chunks in the index so searches skip them. The
        Document is already deleted in Postgres, which Retrieval also checks,
        so a failure here is logged and not raised."""
        try:
            await self.search_index.mark_document_chunks_deleted(
                tenant_id=tenant_id, document_id=document_id
            )
        except (SearchError, CircuitOpenError) as error:
            logger.warning(
                "chunks_not_flagged_deleted",
                tenant_id=str(tenant_id),
                document_id=str(document_id),
                error=str(error),
            )
