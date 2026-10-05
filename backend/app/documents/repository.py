"""Persistence access for the documents domain."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from documents.exceptions import DocumentNotFoundError
from documents.models import (
    Chunk,
    ChunkDeadLetter,
    ChunkDeadLetterStatus,
    ChunkStatus,
    Document,
    DocumentPage,
    IngestionStage,
    IngestionStatus,
    RejectionKind,
    Upload,
    UploadStatus,
)
from tenants.models import Tenant
from users.models import Profile, User


def _uploader_label(
    email: str | None, first_name: str | None, last_name: str | None
) -> str:
    full_name = " ".join(part for part in (first_name, last_name) if part)
    return full_name or email or "someone who has since left"


@dataclass(frozen=True)
class ExistingDocument:
    """A Tenant's live Document with some content, and who uploaded it."""

    name: str
    uploader_email: str | None
    uploader_first_name: str | None
    uploader_last_name: str | None

    @property
    def uploader_label(self) -> str:
        return _uploader_label(
            self.uploader_email, self.uploader_first_name, self.uploader_last_name
        )


@dataclass(frozen=True)
class LibraryDocument:
    """A Tenant's live Document as the Uploads Library lists it."""

    document: Document
    uploader: str


@dataclass(frozen=True)
class DocumentUsage:
    """What a Tenant's non-deleted Documents take up."""

    count: int
    size_bytes: int


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

    async def list_documents_per_tenant(
        self, *, tenant_id: uuid.UUID
    ) -> list[LibraryDocument]:
        """The Tenant's non-deleted Documents, newest first. Bounded by the
        Tenant's Documents Limit, so it is not paginated."""
        result = await self.session.execute(
            select(Document, User.email, Profile.first_name, Profile.last_name)
            .outerjoin(User, User.id == Document.uploader_id)
            .outerjoin(Profile, Profile.user_id == User.id)
            .where(
                Document.tenant_id == tenant_id,
                Document.ingestion_status != IngestionStatus.DELETED,
            )
            .order_by(Document.created_at.desc(), Document.id)
        )
        return [
            LibraryDocument(document, _uploader_label(email, first_name, last_name))
            for document, email, first_name, last_name in result.all()
        ]

    async def count_live_documents_by_status(
        self, *, tenant_id: uuid.UUID
    ) -> dict[str, int]:
        """How many non-deleted Documents the Tenant has in each Ingestion
        Status; a status with none is absent."""
        result = await self.session.execute(
            select(Document.ingestion_status, func.count())
            .where(
                Document.tenant_id == tenant_id,
                Document.ingestion_status != IngestionStatus.DELETED,
            )
            .group_by(Document.ingestion_status)
        )
        return {status: count for status, count in result.all()}

    async def count_pending_uploads_since(
        self, *, user_id: uuid.UUID, since: datetime
    ) -> int:
        """The User's pending Uploads, in any Tenant, started at or after `since`."""
        result = await self.session.execute(
            select(func.count()).where(
                Upload.user_id == user_id,
                Upload.status == UploadStatus.PENDING,
                Upload.created_at >= since,
            )
        )
        return result.scalar_one()

    async def upload_start_times_since(
        self, *, user_id: uuid.UUID, since: datetime
    ) -> list[datetime]:
        """When the User started Uploads at or after `since`, oldest first,
        whatever became of them."""
        result = await self.session.execute(
            select(Upload.created_at)
            .where(Upload.user_id == user_id, Upload.created_at >= since)
            .order_by(Upload.created_at)
        )
        return list(result.scalars())

    async def lock_tenant(self, *, tenant_id: uuid.UUID) -> None:
        """Holds until the transaction ends, so finalizes in a Tenant queue up."""
        await self.session.execute(
            select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()
        )

    async def live_document_usage(self, *, tenant_id: uuid.UUID) -> DocumentUsage:
        result = await self.session.execute(
            select(func.count(), func.coalesce(func.sum(Document.size_bytes), 0)).where(
                Document.tenant_id == tenant_id,
                Document.ingestion_status != IngestionStatus.DELETED,
            )
        )
        count, size_bytes = result.one()
        return DocumentUsage(count=count, size_bytes=int(size_bytes))

    async def get_document(self, document_id: uuid.UUID) -> Document:
        result = await self.session.execute(
            select(Document).where(Document.id == document_id)
        )
        document =  result.scalar_one_or_none()
        if document is None:
            raise DocumentNotFoundError(f"Document with ID {document_id} not found.")
        return document

    async def get_live_document_for_update(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID
    ) -> Document | None:
        """The Tenant's non-deleted Document, row-locked until the transaction
        ends so two deletes of it queue up."""
        result = await self.session.execute(
            select(Document)
            .where(
                Document.id == document_id,
                Document.tenant_id == tenant_id,
                Document.ingestion_status != IngestionStatus.DELETED,
            )
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def mark_document_deleted(
        self, document: Document, *, deleted_by: uuid.UUID
    ) -> None:
        document.ingestion_status = IngestionStatus.DELETED
        document.deleted_at = func.now()
        document.deleted_by = deleted_by
        await self.session.commit()

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

    async def upsert_document_pages(self, pages: Sequence[DocumentPage]) -> None:
        """Insert or update `document_pages` rows in one statement,
        upserting on `(document_id, page_number)` so a retry's full
        re-extraction overwrites a prior attempt's rows instead of
        erroring on the unique constraint (ADR-0010). Does not commit —
        the caller decides the transaction boundary."""
        if not pages:
            return
        statement = pg_insert(DocumentPage).values(
            [
                {
                    "id": page.id,
                    "document_id": page.document_id,
                    "tenant_id": page.tenant_id,
                    "page_number": page.page_number,
                    "text": page.text,
                    "clean_text": page.clean_text,
                    "extraction_method": page.extraction_method,
                    "error_detail": page.error_detail,
                }
                for page in pages
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[DocumentPage.document_id, DocumentPage.page_number],
            set_={
                "text": statement.excluded.text,
                "clean_text": statement.excluded.clean_text,
                "extraction_method": statement.excluded.extraction_method,
                "error_detail": statement.excluded.error_detail,
                "updated_at": func.now(),
            },
        )
        await self.session.execute(statement)

    async def replace_chunks(
        self, document: Document, chunks: Sequence[Chunk], metadata: dict
    ) -> None:
        """Swap all of a Document's Chunks, and its chunking record, for the
        new ones (ADR-0011). Does not commit: delete and insert share the
        caller's transaction, so a retry never leaves duplicates or stale
        rows behind."""
        await self.session.execute(delete(Chunk).where(Chunk.document_id == document.id))
        self.session.add_all(chunks)
        document.chunk_metadata = metadata
        await self.session.flush()

    async def list_pages_with_clean_text(
        self, document_id: uuid.UUID
    ) -> Sequence[DocumentPage]:
        """The Document's pages that have Clean Text (failed pages don't),
        in page order."""
        result = await self.session.execute(
            select(DocumentPage)
            .where(
                DocumentPage.document_id == document_id,
                DocumentPage.clean_text.is_not(None),
            )
            .order_by(DocumentPage.page_number)
        )
        return result.scalars().all()

    async def list_chunks(self, document_id: uuid.UUID) -> Sequence[Chunk]:
        """The Document's Chunks in reading order."""
        result = await self.session.execute(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.ordinal)
        )
        return result.scalars().all()

    async def mark_chunks_indexed(self, chunk_ids: Sequence[uuid.UUID]) -> None:
        """Does not commit: the caller decides the transaction boundary."""
        await self.session.execute(
            update(Chunk)
            .where(Chunk.id.in_(chunk_ids))
            .values(indexing_status=ChunkStatus.DONE, indexing_error=None)
        )

    async def list_chunks_pending_embedding(
        self, document_id: uuid.UUID
    ) -> Sequence[Chunk]:
        """The Document's Chunks that are in the search index and still wait
        for a vector, in reading order."""
        result = await self.session.execute(
            select(Chunk)
            .where(
                Chunk.document_id == document_id,
                Chunk.indexing_status == ChunkStatus.DONE,
                Chunk.embedding_status == ChunkStatus.PENDING,
            )
            .order_by(Chunk.ordinal)
        )
        return result.scalars().all()

    async def mark_chunks_embedded(self, chunk_ids: Sequence[uuid.UUID]) -> None:
        """Does not commit: the caller decides the transaction boundary."""
        await self.session.execute(
            update(Chunk)
            .where(Chunk.id.in_(chunk_ids))
            .values(embedding_status=ChunkStatus.DONE, embedding_error=None)
        )

    async def mark_chunks_indexing_failed(
        self, chunk_ids: Sequence[uuid.UUID], *, error: str
    ) -> None:
        """Does not commit: the caller decides the transaction boundary."""
        await self.session.execute(
            update(Chunk)
            .where(Chunk.id.in_(chunk_ids))
            .values(indexing_status=ChunkStatus.FAILED, indexing_error=error)
        )

    async def add_chunk_dead_letter(self, chunk_dead_letter: ChunkDeadLetter) -> None:
        """Does not commit: written in the same transaction as the Chunks it
        records as failed."""
        self.session.add(chunk_dead_letter)
        await self.session.flush()

    async def list_open_chunk_dead_letters(
        self,
        *,
        stage: IngestionStage,
        document_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> Sequence[ChunkDeadLetter]:
        """Open rows for the stage, oldest first, optionally for one Document
        and capped at `limit`."""
        statement = (
            select(ChunkDeadLetter)
            .where(
                ChunkDeadLetter.status == ChunkDeadLetterStatus.OPEN,
                ChunkDeadLetter.stage == stage,
            )
            .order_by(ChunkDeadLetter.created_at, ChunkDeadLetter.id)
            .limit(limit)
        )
        if document_id is not None:
            statement = statement.where(ChunkDeadLetter.document_id == document_id)
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def get_chunk_dead_letter(
        self, chunk_dead_letter_id: uuid.UUID
    ) -> ChunkDeadLetter | None:
        return await self.session.get(ChunkDeadLetter, chunk_dead_letter_id)

    async def list_chunks_by_ids(
        self, chunk_ids: Sequence[uuid.UUID]
    ) -> Sequence[Chunk]:
        """The listed Chunks that still exist, in reading order."""
        result = await self.session.execute(
            select(Chunk).where(Chunk.id.in_(chunk_ids)).order_by(Chunk.ordinal)
        )
        return result.scalars().all()

    async def list_live_document_ids(self, *, tenant_id: uuid.UUID) -> list[uuid.UUID]:
        """The Tenant's non-deleted Documents: the only ones keyword search
        may return Chunks of."""
        result = await self.session.execute(
            select(Document.id).where(
                Document.tenant_id == tenant_id,
                Document.ingestion_status != IngestionStatus.DELETED,
            )
        )
        return list(result.scalars())
