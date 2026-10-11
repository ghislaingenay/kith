"""Persistence/ORM models for the credits domain."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

# Registers the `asks` table that `ask_id`'s foreign key points at, so a
# process that never imports the asks domain (`make adjust-credits`) can flush.
import asks.models  # noqa: F401
from core.database import Base


class CreditLedgerKind(StrEnum):
    ASK_CHARGE = "ask_charge"
    ADJUSTMENT = "adjustment"


_KIND_VALUES = ", ".join(f"'{kind.value}'" for kind in CreditLedgerKind)


class CreditLedgerEntry(Base):
    """One change to a Tenant's Credit Balance, in signed tokens (ADR-0017).
    Rows are never updated; the balance is their sum."""

    __tablename__ = "credit_ledger"
    __table_args__ = (
        CheckConstraint(f"kind IN ({_KIND_VALUES})", name="ck_credit_ledger_kind"),
        CheckConstraint(
            "kind <> 'adjustment' OR (note IS NOT NULL AND btrim(note) <> '')",
            name="ck_credit_ledger_adjustment_note",
        ),
        Index("ix_credit_ledger_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String, nullable=False)
    tokens: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # SET NULL so an Ask Charge keeps its tokens when its Ask is deleted.
    ask_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("asks.id", ondelete="SET NULL"),
        nullable=True,
    )
    # SET NULL so deleting a User never changes a Tenant's balance.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
