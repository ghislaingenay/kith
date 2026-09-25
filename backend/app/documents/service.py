"""Business logic for uploading PDFs (ADR-0009): start, then finalize."""

import asyncio
import base64
import hashlib
import tempfile
import math
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.exc import IntegrityError

from core.jobs.provider import JobQueue
from core.logging import setup_logger
from core.storage.exceptions import StorageError, StorageObjectNotFoundError
from core.storage.provider import StorageObjectMetadata, StorageProvider
from documents.config import UploadSettings
from documents.display_name import sanitize_display_name
from documents.exceptions import (
    DuplicateDocumentError,
    ContentHashMismatchError,
    InvalidUploadRequestError,
    LimitReachedError,
    RefusedUploadError,
    TooManyPagesError,
    TooManyPendingUploadsError,
    UploadNotFoundError,
    UploadObjectMissingError,
    UploadRateExceededError,
    UploadSizeMismatchError,
)
from documents.keys import document_key, pending_upload_key
from documents.models import Document, RejectionKind, Upload, UploadStatus
from documents.pdf import count_pdf_pages
from documents.repository import DocumentsRepository, ExistingDocument
from documents.schemas import DocumentResponse, InitUploadRequest, InitUploadResponse

logger = setup_logger(__name__)

_PDF_CONTENT_TYPE = "application/pdf"
_INGEST_QUEUE = "ingest"
_INGEST_FUNCTION = "ingest_document"
_RATE_WINDOW = timedelta(hours=1)


class DocumentUploadService:
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

    async def init_upload(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, request: InitUploadRequest
    ) -> InitUploadResponse:
        if request.size > self.settings.max_file_bytes:
            human = _human_size(self.settings.max_file_bytes)
            raise InvalidUploadRequestError(f"File must be {human} or smaller.")
        if request.content_type.lower() != _PDF_CONTENT_TYPE:
            raise InvalidUploadRequestError("Only PDF files can be uploaded.")

        await self._check_user_may_start(user_id)

        declared_sha256 = request.sha256.lower()
        existing = await self.repository.find_live_document_by_hash(
            tenant_id=tenant_id, content_hash=declared_sha256
        )
        if existing:
            raise _duplicate_of(existing)

        await self._check_limits(tenant_id, request.size)

        upload = await self.repository.create_pending_upload(
            tenant_id=tenant_id,
            user_id=user_id,
            filename=sanitize_display_name(request.filename),
            declared_size=request.size,
            declared_sha256=declared_sha256,
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

    async def finalize_upload(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, upload_id: uuid.UUID
    ) -> DocumentResponse:
        upload = await self.repository.get_upload_for_update(
            tenant_id=tenant_id, user_id=user_id, upload_id=upload_id
        )
        if upload is None:
            raise UploadNotFoundError(upload_id)

        if upload.status == UploadStatus.REJECTED:
            raise _refusal_of(upload)
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
        await self._delete_object(pending_upload_key(tenant_id, upload.id))
        return DocumentResponse.model_validate(document)

    async def _check_user_may_start(self, user_id: uuid.UUID) -> None:
        now = datetime.now(UTC)
        starts = await self.repository.upload_start_times_since(
            user_id=user_id, since=now - _RATE_WINDOW
        )
        starts_past_allowance = len(starts) - self.settings.max_starts_per_hour
        if starts_past_allowance >= 0:
            # A slot frees when this many of the oldest starts have left the window.
            retry_after = starts[starts_past_allowance] + _RATE_WINDOW - now
            minutes = max(1, math.ceil(retry_after.total_seconds() / 60))
            raise UploadRateExceededError(
                "You have started too many uploads this hour. "
                f"Try again in {_counted(minutes, 'minute')}.",
                retry_after,
            )

        pending = await self.repository.count_pending_uploads_since(
            user_id=user_id,
            since=now - timedelta(seconds=self.settings.pending_expiry_seconds),
        )
        cap = self.settings.max_pending_per_user
        if pending >= cap:
            raise TooManyPendingUploadsError(
                f"You already have {_counted(cap, 'upload')} in progress. "
                "Wait for one to finish, then try again."
            )

    async def _check_limits(self, tenant_id: uuid.UUID, size: int) -> None:
        usage = await self.repository.live_document_usage(tenant_id=tenant_id)
        limit = self.settings.max_documents
        if usage.count >= limit:
            raise LimitReachedError(
                f"Your workspace has reached its limit of {_counted(limit, 'document')}. "
                "Delete a document to upload another."
            )
        if usage.size_bytes + size > self.settings.max_storage_bytes:
            raise LimitReachedError(
                "This file would take your workspace over its storage limit of "
                f"{_human_size(self.settings.max_storage_bytes)}. "
                "Delete a document to make room."
            )

    async def _accept(self, upload: Upload) -> Document:
        try:
            return await self._validate_and_promote(upload)
        except RefusedUploadError as exc:
            await self.repository.reject_upload(
                upload, reason=str(exc), kind=_rejection_kind_of(exc)
            )
            await self._delete_object(pending_upload_key(upload.tenant_id, upload.id))
            raise

    async def _validate_and_promote(self, upload: Upload) -> Document:
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
            if content_hash != upload.declared_sha256:
                raise ContentHashMismatchError(
                    "The file arrived corrupt. Please try uploading it again."
                )
            page_count = await asyncio.to_thread(count_pdf_pages, path)
            if page_count > self.settings.max_pages:
                raise TooManyPagesError(
                    f"The PDF has {page_count} pages; the limit is "
                    f"{self.settings.max_pages} pages per file. Split it and "
                    "upload the parts."
                )

        await self.repository.lock_tenant(tenant_id=upload.tenant_id)
        existing = await self.repository.find_live_document_by_hash(
            tenant_id=upload.tenant_id, content_hash=content_hash
        )
        if existing:
            raise _duplicate_of(existing)
        await self._check_limits(upload.tenant_id, downloaded_size)

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
        try:
            await self.repository.complete_upload(upload, document)
        except IntegrityError:
            # Another finalize of the same content committed first.
            existing = await self.repository.find_live_document_by_hash(
                tenant_id=upload.tenant_id, content_hash=content_hash
            )
            if existing is None:
                raise
            await self._delete_object(permanent_key)
            raise _duplicate_of(existing) from None
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

    async def _delete_object(self, key: str) -> None:
        try:
            await self.storage.delete(key)
        except StorageError:
            # Best effort: the cleanup sweep and the bucket's lifecycle rule
            # remove what this leaves behind.
            logger.warning("Could not delete upload object", key=key)


# Most specific first: `RefusedUploadError` is the base of the others.
_REFUSAL_BY_KIND: dict[RejectionKind, type[RefusedUploadError]] = {
    RejectionKind.DUPLICATE: DuplicateDocumentError,
    RejectionKind.LIMIT_REACHED: LimitReachedError,
    RejectionKind.INVALID_FILE: RefusedUploadError,
}


def _rejection_kind_of(refusal: RefusedUploadError) -> RejectionKind:
    return next(
        kind
        for kind, refusal_type in _REFUSAL_BY_KIND.items()
        if isinstance(refusal, refusal_type)
    )


def _refusal_of(upload: Upload) -> RefusedUploadError:
    """The refusal a rejected Upload was given, so finalizing it again
    answers as the first finalize did."""
    refusal_type = _REFUSAL_BY_KIND.get(
        RejectionKind(upload.rejection_kind), RefusedUploadError
    )
    return refusal_type(upload.rejection_reason)


def _counted(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _human_size(size: int) -> str:
    if size < 1024:
        return f"{size} bytes"
    if size < 1024 * 1024:
        return f"{(size + 1023) // 1024} KB"
    return f"{(size + (1024 * 1024 - 1)) // (1024 * 1024)} MB"


def _duplicate_of(existing: ExistingDocument) -> DuplicateDocumentError:
    return DuplicateDocumentError(
        f'"{existing.name}" was already uploaded by {existing.uploader_label}.'
    )
