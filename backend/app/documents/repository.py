"""Persistence access for the documents domain."""

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from documents.models import (
    Document,
    IngestionStatus,
    RejectionKind,
    Upload,
    UploadStatus,
)
from users.models import Profile, User


@dataclass(frozen=True)
class ExistingDocument:
    """A Tenant's live Document with some content, and who uploaded it."""

    name: str
    uploader_email: str | None
    uploader_first_name: str | None
    uploader_last_name: str | None

    @property
    def uploader_label(self) -> str:
        full_name = " ".join(
            part for part in (self.uploader_first_name, self.uploader_last_name) if part
        )
        return full_name or self.uploader_email or "someone who has since left"


class DocumentsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_pending_upload(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        filename: str,
        declared_size: int,
        declared_sha256: str,
    ) -> Upload:
        upload = Upload(
            tenant_id=tenant_id,
            user_id=user_id,
            filename=filename,
            declared_size=declared_size,
            declared_sha256=declared_sha256,
        )
        self.session.add(upload)
        await self.session.commit()
        return upload

    async def get_upload_for_update(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, upload_id: uuid.UUID
    ) -> Upload | None:
        """The caller's own Upload in this Tenant, row-locked until the
        transaction ends so a second finalize of it waits for the first."""
        result = await self.session.execute(
            select(Upload)
            .where(
                Upload.id == upload_id,
                Upload.tenant_id == tenant_id,
                Upload.user_id == user_id,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def find_live_document_by_hash(
        self, *, tenant_id: uuid.UUID, content_hash: str
    ) -> ExistingDocument | None:
        result = await self.session.execute(
            select(
                Document.name,
                User.email,
                Profile.first_name,
                Profile.last_name,
            )
            .outerjoin(User, User.id == Document.uploader_id)
            .outerjoin(Profile, Profile.user_id == User.id)
            .where(
                Document.tenant_id == tenant_id,
                Document.content_hash == content_hash,
                Document.ingestion_status != IngestionStatus.DELETED,
            )
        )
        row = result.first()
        return ExistingDocument(*row) if row else None

    async def get_document(self, document_id: uuid.UUID) -> Document:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one()

    async def complete_upload(self, upload: Upload, document: Document) -> None:
        """Insert the Document and mark the Upload completed in one
        transaction. The insert runs in a savepoint so that, if the unique
        index on Tenant plus Content Hash refuses it (`IntegrityError`), the
        Upload can still be updated in the same transaction."""
        async with self.session.begin_nested():
            self.session.add(document)
            await self.session.flush()
        upload.status = UploadStatus.COMPLETED
        upload.document_id = document.id
        await self.session.commit()

    async def reject_upload(
        self, upload: Upload, *, reason: str, kind: RejectionKind
    ) -> None:
        upload.status = UploadStatus.REJECTED
        upload.rejection_reason = reason
        upload.rejection_kind = kind
        await self.session.commit()
