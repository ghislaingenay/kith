"""Business logic for uploading PDFs (ADR-0009): start, then finalize."""

import asyncio
import base64
import hashlib
import tempfile
import uuid
from pathlib import Path

from core.jobs.provider import JobQueue
from core.logging import setup_logger
from core.storage.exceptions import StorageError, StorageObjectNotFoundError
from core.storage.provider import StorageObjectMetadata, StorageProvider
from documents.config import UploadSettings
from documents.display_name import sanitize_display_name
from documents.exceptions import (
    InvalidUploadRequestError,
    UploadNotFoundError,
    UploadObjectMissingError,
    UploadSizeMismatchError,
)
from documents.keys import document_key, pending_upload_key
from documents.models import Document, Upload, UploadStatus
from documents.pdf import count_pdf_pages
from documents.repository import DocumentsRepository
from documents.schemas import DocumentResponse, InitUploadRequest, InitUploadResponse

logger = setup_logger(__name__)

_PDF_CONTENT_TYPE = "application/pdf"
_INGEST_QUEUE = "ingest"
_INGEST_FUNCTION = "ingest_document"


class UploadService:
    def __init__(
        self,
        repository: DocumentsRepository,
        storage: StorageProvider,
        job_queue: JobQueue,
        settings: UploadSettings,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.job_queue = job_queue
        self.settings = settings

    async def start(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, request: InitUploadRequest
    ) -> InitUploadResponse:
        if request.size > self.settings.max_file_bytes:
            raise InvalidUploadRequestError(
                f"File must be {self.settings.max_file_bytes // (1024 * 1024)} MB or smaller."
            )
        if request.content_type.lower() != _PDF_CONTENT_TYPE:
            raise InvalidUploadRequestError("Only PDF files can be uploaded.")

        upload = await self.repository.create_pending_upload(
            tenant_id=tenant_id,
            user_id=user_id,
            filename=sanitize_display_name(request.filename),
            declared_size=request.size,
        )
        checksum = base64.b64encode(bytes.fromhex(request.sha256)).decode()
        url = await self.storage.generate_presigned_put(
            pending_upload_key(tenant_id, upload.id),
            self.settings.presigned_url_ttl_seconds,
            content_type=_PDF_CONTENT_TYPE,
            content_length=request.size,
            checksum_sha256=checksum,
        )
        return InitUploadResponse(
            upload_id=upload.id,
            url=url,
            headers={
                "Content-Type": _PDF_CONTENT_TYPE,
                "x-amz-checksum-sha256": checksum,
            },
            expires_in=self.settings.presigned_url_ttl_seconds,
        )

    async def finalize(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, upload_id: uuid.UUID
    ) -> DocumentResponse:
        upload = await self.repository.get_upload_for_update(
            tenant_id=tenant_id, user_id=user_id, upload_id=upload_id
        )
        if upload is None:
            raise UploadNotFoundError(upload_id)

        if upload.status == UploadStatus.COMPLETED and upload.document_id:
            document = await self.repository.get_document(upload.document_id)
        else:
            document = await self._accept(upload)

        await self.job_queue.enqueue(
            _INGEST_QUEUE,
            _INGEST_FUNCTION,
            {"document_id": str(document.id), "tenant_id": str(tenant_id)},
            job_id=str(document.id),
        )
        await self._delete_temporary_object(pending_upload_key(tenant_id, upload.id))
        return DocumentResponse.model_validate(document)

    async def _accept(self, upload: Upload) -> Document:
        temporary_key = pending_upload_key(upload.tenant_id, upload.id)
        stored = await self._head_temporary_object(temporary_key)
        if stored.size != upload.declared_size:
            raise UploadSizeMismatchError(
                "The file that arrived is not the size that was announced."
            )

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "upload.pdf"
            content_hash, downloaded_size = await self._download_hashing(
                temporary_key, path
            )
            # The link stays valid for minutes, so the object can be replaced
            # after `head`; what was hashed must be what was announced.
            if downloaded_size != upload.declared_size:
                raise UploadSizeMismatchError(
                    "The file that arrived is not the size that was announced."
                )
            page_count = await asyncio.to_thread(count_pdf_pages, path)

        document_id = uuid.uuid4()
        permanent_key = document_key(upload.tenant_id, document_id)
        await self.storage.copy(temporary_key, permanent_key)
        document = Document(
            id=document_id,
            tenant_id=upload.tenant_id,
            uploader_id=upload.user_id,
            name=upload.filename,
            size_bytes=downloaded_size,
            page_count=page_count,
            content_hash=content_hash,
            storage_key=permanent_key,
        )
        await self.repository.complete_upload(upload, document)
        return document

    async def _head_temporary_object(self, key: str) -> StorageObjectMetadata:
        try:
            return await self.storage.head(key)
        except StorageObjectNotFoundError as exc:
            raise UploadObjectMissingError(
                "The file has not been received yet."
            ) from exc

    async def _download_hashing(self, key: str, path: Path) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0
        file = await asyncio.to_thread(path.open, "wb")
        try:
            async for chunk in self.storage.download(key):
                digest.update(chunk)
                size += len(chunk)
                await asyncio.to_thread(file.write, chunk)
        finally:
            await asyncio.to_thread(file.close)
        return digest.hexdigest(), size

    async def _delete_temporary_object(self, key: str) -> None:
        try:
            await self.storage.delete(key)
        except StorageError:
            # The Document is already committed; the cleanup sweep and the
            # bucket's lifecycle rule remove what this leaves behind.
            logger.warning("Could not delete temporary upload object", key=key)
