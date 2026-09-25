"""Persistence access for the documents domain."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from documents.models import Document, Upload, UploadStatus


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
    ) -> Upload:
        upload = Upload(
            tenant_id=tenant_id,
            user_id=user_id,
            filename=filename,
            declared_size=declared_size,
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

    async def get_document(self, document_id: uuid.UUID) -> Document:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one()

    async def complete_upload(self, upload: Upload, document: Document) -> None:
        """Insert the Document and mark the Upload completed in one
        transaction."""
        self.session.add(document)
        await self.session.flush()
        upload.status = UploadStatus.COMPLETED
        upload.document_id = document.id
        await self.session.commit()
