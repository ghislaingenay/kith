"""Business logic for the Uploads Library: what a Tenant holds."""

import uuid

from documents.models import IngestionStatus
from documents.repository import DocumentsRepository
from documents.schemas import LibraryDocumentResponse, LibrarySummaryResponse

_IN_PROGRESS = (IngestionStatus.UPLOADED, IngestionStatus.PROCESSING)


class DocumentLibraryService:
    """Service layer for managing a Tenant's Uploads Library."""
    def __init__(self, repository: DocumentsRepository) -> None:
        self.repository = repository

    async def list_documents(
        self, *, tenant_id: uuid.UUID
    ) -> list[LibraryDocumentResponse]:
        documents = await self.repository.list_documents_per_tenant(tenant_id=tenant_id)
        return [
            LibraryDocumentResponse(
                id=document.document.id,
                name=document.document.name,
                size_bytes=document.document.size_bytes,
                uploader=document.uploader,
                created_at=document.document.created_at,
                ingestion_status=document.document.ingestion_status,
                ingestion_stage=document.document.ingestion_stage,
                pages_extracted=document.document.pages_extracted,
                page_count=document.document.page_count,
            )
            for document in documents
        ]

    async def summarize(self, *, tenant_id: uuid.UUID) -> LibrarySummaryResponse:
        counts = await self.repository.count_live_documents_by_status(
            tenant_id=tenant_id
        )
        return LibrarySummaryResponse(
            in_progress=sum(counts.get(status, 0) for status in _IN_PROGRESS),
            failed=counts.get(IngestionStatus.FAILED, 0),
        )
