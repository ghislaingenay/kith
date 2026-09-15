"""Persistence/ORM models for the tenant domain."""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base


class Tenant(Base):
    """An organization/workspace that owns users, subject to its own
    feature entitlements."""

    __tablename__ = "tenants"
    __table_args__ = (
        CheckConstraint(
            "tier IN ('free', 'professional', 'enterprise')",
            name="ck_tenants_tier",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    tier: Mapped[str] = mapped_column(String, nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, nullable=False)
    features: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TenantMembership(Base):
    """Membership: links a User (identity) to a Tenant with a Role.
    Many-to-many — composite PK (tenant_id, user_id) is the only
    uniqueness constraint, so one identity can hold multiple rows (one per
    tenant it belongs to). Which one is "active" for a given request is
    resolved per-request via the X-Tenant-ID header, not stored here —
    see auth/dependencies.py.

    `deactivated_at` ends a membership (e.g. the identity behind it was
    soft-deleted) without losing the tenant/role history."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (Index("idx_tenant_memberships_role_id", "role_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id"), nullable=False
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
    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
