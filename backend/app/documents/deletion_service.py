"""Business logic for deleting Documents."""

import uuid

from core.jobs.provider import JobQueue
from documents.exceptions import DocumentNotFoundError
from documents.repository import DocumentsRepository
from tenants.exceptions import PermissionDenied
from tenants.permissions import Action, Role, has_permission

_TASKS_QUEUE = "tasks"
_PURGE_FUNCTION = "purge_document"


class DocumentDeletionService:
    def __init__(self, repository: DocumentsRepository, job_queue: JobQueue) -> None:
        self.repository = repository
        self.job_queue = job_queue

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
