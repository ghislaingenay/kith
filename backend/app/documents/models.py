"""Persistence/ORM models for the documents domain."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class IngestionStatus(StrEnum):
    """Where a Document is in Ingestion (CONTEXT.md). A Document is created
    as `UPLOADED`; the worker moves it on."""

    UPLOADED = "uploaded"
    PROCESSING = "processing"
    PARTIAL = "partial"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class IngestionStage(StrEnum):
    """The step of Ingestion a `PROCESSING` Document is in."""

    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    INDEXING = "indexing"


class UploadStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    EXPIRED = "expired"
    REJECTED = "rejected"

class DocumentSource(StrEnum):
    PDF = "pdf"

_DOCUMENT_SOURCE_VALUES = ", ".join(f"'{source.value}'" for source in DocumentSource)

_INGESTION_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in IngestionStatus)
_INGESTION_STAGE_VALUES = ", ".join(f"'{stage.value}'" for stage in IngestionStage)
_UPLOAD_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in UploadStatus)


class Document(Base):
    """A PDF a User uploaded into a Tenant. Only exists once an Upload was
    accepted. `ingestion_stage` and `pages_extracted` are written by the
    ingestion worker; the API only reads them."""

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            f"ingestion_status IN ({_INGESTION_STATUS_VALUES})",
            name="ck_documents_ingestion_status",
        ),
        CheckConstraint(
            f"ingestion_stage IN ({_INGESTION_STAGE_VALUES})",
            name="ck_documents_ingestion_stage",
        ),
        Index(
            "uq_documents_tenant_content_hash_active",
            "tenant_id",
            "content_hash",
            unique=True,
            postgresql_where=text(f"ingestion_status <> '{IngestionStatus.DELETED}'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploader_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(
        String, nullable=False, default=DocumentSource.PDF
    )
    ingestion_status: Mapped[str] = mapped_column(
        String, nullable=False, default=IngestionStatus.UPLOADED
    )
    ingestion_stage: Mapped[str | None] = mapped_column(
        String, nullable=True, default=None
    )
    pages_extracted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Upload(Base):
    """One attempt to move a PDF's bytes into a Tenant (CONTEXT.md). A
    completed Upload links to the Document it produced."""

    __tablename__ = "uploads"
    __table_args__ = (
        CheckConstraint(
            f"status IN ({_UPLOAD_STATUS_VALUES})",
            name="ck_uploads_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String, nullable=False, default=UploadStatus.PENDING
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    declared_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    declared_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
