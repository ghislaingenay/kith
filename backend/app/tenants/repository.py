"""Persistence access for the tenants domain."""

import re
import uuid
from typing import NamedTuple

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tenants.models import PendingMembership, Tenant, TenantMembership
from tenants.permissions import Role


class MembershipDetails(NamedTuple):
    """The display shape for /tenants and /me's memberships list — still
    unpacks positionally like a plain tuple, so existing callers (and
    fakes in tests) that destructure it don't need to change; naming the
    fields just keeps `list_active_membership_details`/`create_tenant`'s
    growing return shape from being a bag of positional primitives."""

    membership: TenantMembership
    tenant_name: str
    tenant_slug: str
    role: Role

_DEFAULT_TENANT_TIER = "free"
_DEFAULT_TENANT_MAX_USERS = (
    5  # MVP default seat count; revisit if there's a billing-driven policy
)
# Arbitrary namespace for pg_advisory_xact_lock's two-int32 key, so this
# lock class can't collide with an unrelated advisory lock taken elsewhere
# in the app on the same connection.
_TENANT_CREATION_LOCK_NAMESPACE = 7_814_991


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "tenant"


def _default_tenant_name(first_name: str | None, email: str) -> str:
    owner_label = first_name or (email.split("@", 1)[0] or "user")
    return f"{owner_label}'s organization"


def _default_tenant_slug(name: str, user_id: uuid.UUID) -> str:
    """Deterministic per-user, not per-call — a retried provisioning
    attempt for the same user always computes the same slug, which is
    what makes the ON CONFLICT (slug) DO NOTHING + re-select below safe."""
    return f"{_slugify(name)[:80]}-{user_id.hex[:8]}"


class TenantsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_membership(
        self, *, user_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> TenantMembership | None:
        result = await self.session.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.deactivated_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def acquire_user_tenant_lock(self, user_id: uuid.UUID) -> None:
        """Blocks until an exclusive, transaction-scoped Postgres advisory
        lock keyed on `user_id` is acquired — released automatically when
        the current transaction commits or rolls back. Call this before
        checking "does this user already have a tenant" so the check and
        the subsequent insert become atomic across concurrent requests for
        the same user; see TenantsService.create_tenant. This is
        service-layer policy enforcement, not a schema constraint —
        TenantMembership's own uniqueness stays the composite
        (tenant_id, user_id) PK (see models.py), so the repository itself
        still permits multiple tenants per user (test_repository.py's
        `test_two_calls_with_same_name_create_distinct_tenants`)."""
        await self.session.execute(
            select(
                func.pg_advisory_xact_lock(
                    _TENANT_CREATION_LOCK_NAMESPACE, func.hashtext(str(user_id))
                )
            )
        )

    async def list_active_membership_details(
        self, user_id: uuid.UUID
    ) -> list[MembershipDetails]:
        """The Role comes straight off the membership row, no Roles table
        to join. Ordered deterministically (created_at, tenant_id) so a
        caller picking "the first membership" gets a stable answer across
        calls rather than whatever order Postgres happens to return rows
        in."""
        result = await self.session.execute(
            select(TenantMembership, Tenant.name, Tenant.slug)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .where(
                TenantMembership.user_id == user_id,
                TenantMembership.deactivated_at.is_(None),
            )
            .order_by(TenantMembership.created_at, TenantMembership.tenant_id)
        )
        return [
            MembershipDetails(row[0], row[1], row[2], Role(row[0].role))
            for row in result.all()
        ]

    async def get_earliest_pending_membership(
        self, email: str
    ) -> PendingMembership | None:
        """The one Pending Membership TenantsService.activate_pending_membership
        will activate for `email` — deterministically the earliest-created
        (created_at, tenant_id) row, so a caller with several tenants'
        invites waiting for the same email always resolves to the same
        one across calls. `None` if nothing is pending for this email."""
        result = await self.session.execute(
            select(PendingMembership)
            .where(PendingMembership.email == email)
            .order_by(PendingMembership.created_at, PendingMembership.tenant_id)
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def activate_pending_membership(
        self, *, user_id: uuid.UUID, tenant_id: uuid.UUID, email: str
    ) -> TenantMembership | None:
        """Activates the Pending Membership at `(tenant_id, email)` — its
        composite PK — converting it into a real TenantMembership carrying
        its stored Role and deleting the Pending Membership row. Returns
        `None` if no such row exists.

        Deliberately scoped to one exact row, not "every Pending
        Membership matching this email": which row to activate when
        several tenants have invited the same email is a business
        decision (this app enforces one active tenant per user — see
        TenantAlreadyExistsError — and switching between tenants is out of
        scope this pass, ADR-0008) that TenantsService.activate_pending_membership
        makes before calling this; this method just carries it out on the
        exact key it's given.

        ON CONFLICT DO NOTHING guards against the row already existing as
        a TenantMembership (e.g. this ran once already for a retried
        verify)."""
        pending = await self.session.get(PendingMembership, (tenant_id, email))
        if pending is None:
            return None

        membership_insert = (
            insert(TenantMembership)
            .values(tenant_id=tenant_id, user_id=user_id, role=pending.role)
            .on_conflict_do_nothing(
                index_elements=[TenantMembership.tenant_id, TenantMembership.user_id]
            )
            .returning(TenantMembership)
        )
        result = await self.session.execute(membership_insert)
        membership = result.scalar_one_or_none()
        if membership is None:
            membership = await self.get_active_membership(
                user_id=user_id, tenant_id=tenant_id
            )
        await self.session.delete(pending)
        await self.session.commit()
        return membership

    async def provision_default_membership(
        self, *, user_id: uuid.UUID, email: str, first_name: str | None = None
    ) -> TenantMembership:
        """First-time-only: auto-create a Tenant named after the user (or
        their email, if no first name is available) and assign the
        'owner' role. Only called by UserReconciliationService when
        upsert_identity reported created=True, so it does not need its own
        lock for "one default membership per user" — tenant_memberships has
        no such uniqueness now that membership is many-to-many. Tenant
        creation itself still goes through INSERT ... ON CONFLICT (slug) DO
        NOTHING + re-select, as a safety net against a retried call."""
        name = _default_tenant_name(first_name, email)
        slug = _default_tenant_slug(name, user_id)

        tenant_insert = (
            insert(Tenant)
            .values(
                name=name,
                slug=slug,
                tier=_DEFAULT_TENANT_TIER,
                max_users=_DEFAULT_TENANT_MAX_USERS,
            )
            .on_conflict_do_nothing(index_elements=[Tenant.slug])
            .returning(Tenant.id)
        )
        result = await self.session.execute(tenant_insert)
        tenant_id = result.scalar_one_or_none()
        if tenant_id is None:
            tenant_id = await self.session.scalar(
                select(Tenant.id).where(Tenant.slug == slug)
            )

        membership_insert = (
            insert(TenantMembership)
            .values(tenant_id=tenant_id, user_id=user_id, role=Role.OWNER)
            .on_conflict_do_nothing(
                index_elements=[TenantMembership.tenant_id, TenantMembership.user_id]
            )
            .returning(TenantMembership)
        )
        result = await self.session.execute(membership_insert)
        await self.session.commit()
        membership = result.scalar_one_or_none()
        if membership is None:
            membership = await self.get_active_membership(
                user_id=user_id, tenant_id=tenant_id
            )
        return membership

    async def create_tenant(self, *, user_id: uuid.UUID, name: str) -> MembershipDetails:
        """Explicit, user-initiated action: an already-authenticated
        identity creates a new tenant and becomes its owner. Not idempotent
        like provision_default_membership — each call makes a brand-new
        Tenant even if `name` repeats (two tenants may share a display
        name), safe because the slug embeds a random suffix rather than a
        deterministic per-user hash, so there's nothing to retry into a
        collision.

        This method itself enforces no per-user limit — callers that need
        "one active tenant per user" (currently TenantsService.create_tenant)
        must check eligibility themselves, e.g. via
        acquire_user_tenant_lock() + list_active_membership_details()."""
        slug = f"{_slugify(name)[:80]}-{uuid.uuid4().hex[:8]}"

        tenant = Tenant(
            name=name,
            slug=slug,
            tier=_DEFAULT_TENANT_TIER,
            max_users=_DEFAULT_TENANT_MAX_USERS,
        )
        self.session.add(tenant)
        await self.session.flush()

        membership = TenantMembership(
            tenant_id=tenant.id, user_id=user_id, role=Role.OWNER
        )
        self.session.add(membership)
        await self.session.commit()
        return MembershipDetails(membership, tenant.name, tenant.slug, Role.OWNER)
