"""Persistence/ORM models for the tenant domain."""

import uuid
from datetime import datetime
from enum import StrEnum

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
from tenants.permissions import Role

_ROLE_VALUES = ", ".join(f"'{role.value}'" for role in Role)


class PendingMembershipStatus(StrEnum):
    """Lifecycle of a Pending Membership row (ADR-0008). Only `PENDING` rows
    are live; the rest are kept as history."""

    PENDING = "pending"
    ACCEPTED = "accepted"  # the email signed in and a TenantMembership was created
    REVOKED = "revoked"  # an Admin withdrew it before it was accepted
    EXPIRED = "expired"  # aged past the TTL and was closed by a re-add


_PENDING_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in PendingMembershipStatus)


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
    __table_args__ = (
        CheckConstraint(
            f"role IN ({_ROLE_VALUES})",
            name="ck_tenant_memberships_role",
        ),
    )

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
    role: Mapped[str] = mapped_column(String, nullable=False)
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


class PendingMembership(Base):
    """A Tenant Membership an Admin created for an email that has not
    signed in yet (ADR-0008, CONTEXT.md). There is no token: it sits here
    until that email's first sign-in activates it into a real
    TenantMembership carrying this Role, at which point the row is kept and
    its status moves to `accepted` (see TenantsRepository).

    Surrogate `id` as the key so history rows can accumulate: the only
    uniqueness rule is the partial index below, one *pending* row per
    (tenant, email) — a (tenant_id, email) primary key would allow a single
    row ever. `email` is stored trimmed and lowercased, enforced by a CHECK
    so no code path can add `Alice@x.com` beside `alice@x.com`."""

    __tablename__ = "pending_memberships"
    __table_args__ = (
        CheckConstraint(
            f"role IN ({_ROLE_VALUES})",
            name="ck_pending_memberships_role",
        ),
        CheckConstraint(
            f"status IN ({_PENDING_STATUS_VALUES})",
            name="ck_pending_memberships_status",
        ),
        CheckConstraint(
            "email = lower(btrim(email))",
            name="ck_pending_memberships_email_normalized",
        ),
        Index(
            "uq_pending_memberships_one_pending",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
        Index("idx_pending_memberships_email", "email"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default=PendingMembershipStatus.PENDING,
        server_default=PendingMembershipStatus.PENDING.value,
    )
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
