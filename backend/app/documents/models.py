"""Persistence/ORM models for the documents domain."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
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


class RejectionKind(StrEnum):
    """Why an Upload was rejected, so a repeated finalize can answer the way
    the first one did."""

    DUPLICATE = "duplicate"
    INVALID_FILE = "invalid_file"
    LIMIT_REACHED = "limit_reached"


class ChunkStatus(StrEnum):
    """Where a Chunk is in indexing or embedding (ADR-0011): every Chunk
    starts `PENDING` in both."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class DocumentSource(StrEnum):
    PDF = "pdf"


class ExtractionMethod(StrEnum):
    """How a `DocumentPage` row's text (if any) was produced (ADR-0010)."""

    TEXT_LAYER = "text_layer"
    EXTRACTION_ERROR = "extraction_error"


_DOCUMENT_SOURCE_VALUES = ", ".join(f"'{source.value}'" for source in DocumentSource)

_INGESTION_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in IngestionStatus)
_INGESTION_STAGE_VALUES = ", ".join(f"'{stage.value}'" for stage in IngestionStage)
_UPLOAD_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in UploadStatus)
_REJECTION_KIND_VALUES = ", ".join(f"'{kind.value}'" for kind in RejectionKind)
_CHUNK_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in ChunkStatus)
_EXTRACTION_METHOD_VALUES = ", ".join(
    f"'{method.value}'" for method in ExtractionMethod
)


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
        CheckConstraint(
            f"(ingestion_status = '{IngestionStatus.DELETED}') = (deleted_at IS NOT NULL)",
            name="ck_documents_deleted_at_iff_deleted",
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
    ingestion_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Human-readable reason a Document ended `FAILED` (ADR-0010)."""
    chunk_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    """How the Document's current Chunks were made (ADR-0011): size, overlap,
    cleaner version, tokenizer and time. Overwritten by a retry, no history."""
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Set exactly when `ingestion_status` is `DELETED`; the status stays the
    filter of record for a valid Document."""
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class DocumentPage(Base):
    """One page's extracted text (ADR-0002, ADR-0010). Keeps no history —
    a retry re-extracts every page from 1 and upserts over what's here,
    never a partial resume."""

    __tablename__ = "document_pages"
    __table_args__ = (
        CheckConstraint(
            f"extraction_method IN ({_EXTRACTION_METHOD_VALUES})",
            name="ck_document_pages_extraction_method",
        ),
        # Retries re-extract every page from 1 (ADR-0010): this unique
        # index exists so a retry's writes upsert cleanly onto a prior
        # attempt's rows, not to prevent duplicates that could otherwise
        # occur.
        Index(
            "uq_document_pages_document_id_page_number",
            "document_id",
            "page_number",
            unique=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Page Text: raw, exactly as extraction produced it."""
    clean_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    """Clean Text (ADR-0011): `text` after cleanup; empty for a blank page,
    null when the page's extraction failed."""
    extraction_method: Mapped[str] = mapped_column(String, nullable=False)
    ocr_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    """Reserved for a future OCR pass; unused until OCR extraction exists."""
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Chunk(Base):
    """A passage of one page's Clean Text (ADR-0002, ADR-0011). Never spans
    two pages; `char_start`/`char_end` slice the page's stored Clean Text to
    exactly `text`, or are both null when that could not be verified."""

    __tablename__ = "chunks"
    __table_args__ = (
        CheckConstraint(
            f"indexing_status IN ({_CHUNK_STATUS_VALUES})",
            name="ck_chunks_indexing_status",
        ),
        CheckConstraint(
            f"embedding_status IN ({_CHUNK_STATUS_VALUES})",
            name="ck_chunks_embedding_status",
        ),
        Index("uq_chunks_document_id_ordinal", "document_id", "ordinal", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    """Position within the whole Document, from 0."""
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    indexing_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=ChunkStatus.PENDING,
        server_default=ChunkStatus.PENDING,
    )
    indexing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=ChunkStatus.PENDING,
        server_default=ChunkStatus.PENDING,
    )
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        CheckConstraint(
            f"rejection_kind IN ({_REJECTION_KIND_VALUES})",
            name="ck_uploads_rejection_kind",
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
    rejection_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
