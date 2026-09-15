"""Persistence access for the tenants domain."""

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from rbac.models import Role
from tenants.exceptions import OwnerRoleNotConfiguredError
from tenants.models import Tenant, TenantMembership

_DEFAULT_TENANT_TIER = "free"
_DEFAULT_TENANT_MAX_USERS = (
    5  # MVP default seat count; revisit if there's a billing-driven policy
)
_DEFAULT_TENANT_ROLE_NAME = "owner"
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
    ) -> list[tuple[TenantMembership, str, str]]:
        """(membership, tenant_name, role_name) tuples — the display shape
        for /tenants and /me's memberships list."""
        result = await self.session.execute(
            select(TenantMembership, Tenant.name, Role.name)
            .join(Tenant, Tenant.id == TenantMembership.tenant_id)
            .join(Role, Role.id == TenantMembership.role_id)
            .where(
                TenantMembership.user_id == user_id,
                TenantMembership.deactivated_at.is_(None),
            )
        )
        return [(row[0], row[1], row[2]) for row in result.all()]

    async def _get_owner_role_id(self) -> uuid.UUID:
        role_id = await self.session.scalar(
            select(Role.id).where(Role.name == _DEFAULT_TENANT_ROLE_NAME)
        )
        if role_id is None:
            raise OwnerRoleNotConfiguredError()
        return role_id

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

        role_id = await self._get_owner_role_id()

        membership_insert = (
            insert(TenantMembership)
            .values(tenant_id=tenant_id, user_id=user_id, role_id=role_id)
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

    async def create_tenant(
        self, *, user_id: uuid.UUID, name: str
    ) -> tuple[TenantMembership, str, str]:
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
        role_id = await self._get_owner_role_id()

        tenant = Tenant(
            name=name,
            slug=slug,
            tier=_DEFAULT_TENANT_TIER,
            max_users=_DEFAULT_TENANT_MAX_USERS,
        )
        self.session.add(tenant)
        await self.session.flush()

        membership = TenantMembership(
            tenant_id=tenant.id, user_id=user_id, role_id=role_id
        )
        self.session.add(membership)
        await self.session.commit()
        return membership, tenant.name, _DEFAULT_TENANT_ROLE_NAME
