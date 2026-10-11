"""Persistence/ORM models for the asks domain."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class AskStatus(StrEnum):
    COMPLETED = "completed"
    CUT_OFF = "cut_off"
    FAILED = "failed"
    NO_CHUNKS = "no_chunks"


_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in AskStatus)


class Ask(Base):
    """A Query answered from its own Retrieval (CONTEXT.md). Token counts are
    `None` when the provider reported none."""

    __tablename__ = "asks"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="ck_asks_status"),
        Index("ix_asks_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Deleting a User deletes their Asks (mvp-design §2); their Ask Charges stay.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    cited_chunks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    """In the order they were numbered for the model: `chunk_id`,
    `document_id`, `page_number`, `rerank_score` (or null)."""
    is_reranked: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_degraded: Mapped[bool] = mapped_column(Boolean, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reasoning_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
