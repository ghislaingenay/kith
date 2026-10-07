"""Business logic for reading a Document's PDF in the browser."""

import uuid

from core.storage.provider import StorageProvider
from documents.config import PreviewSettings
from documents.exceptions import DocumentNotFoundError
from documents.repository import DocumentsRepository
from documents.schemas import DocumentFileUrlResponse


class DocumentFileService:
    def __init__(
        self,
        repository: DocumentsRepository,
        storage: StorageProvider,
        settings: PreviewSettings,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.settings = settings

    async def get_file_url(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> DocumentFileUrlResponse:
        """A short-lived link the browser reads the Document's PDF from."""
        document = await self.repository.get_live_document(
            tenant_id=tenant_id, document_id=document_id
        )
        if document is None:
            raise DocumentNotFoundError(f"Document {document_id} not found.")
        ttl = self.settings.preview_url_ttl_seconds
        url = await self.storage.generate_presigned_url(document.storage_key, "GET", ttl)
        return DocumentFileUrlResponse(url=url, expires_in=ttl)
