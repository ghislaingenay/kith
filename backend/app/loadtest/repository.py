"""Persistence access for Load Test Tenants and their Memberships."""

import uuid

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from tenants.models import Tenant, TenantMembership
from tenants.permissions import Role


class LoadTestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def upsert_tenant(self, *, slug: str, name: str, max_users: int) -> uuid.UUID:
        """Creates the Tenant, or re-uses the one with this slug: live again
        if it was deleted, with at least `max_users` seats."""
        statement = insert(Tenant).values(
            name=name, slug=slug, tier="free", max_users=max_users
        )
        statement = statement.on_conflict_do_update(
            index_elements=[Tenant.slug],
            set_={
                "max_users": func.greatest(Tenant.max_users, max_users),
                "is_active": True,
                "deleted_at": None,
            },
        ).returning(Tenant.id)
        return await self.session.scalar(statement)

    async def set_only_membership(
        self, *, user_id: uuid.UUID, tenant_id: uuid.UUID, role: Role
    ) -> None:
        """Makes `tenant_id` the User's one live Membership, closing (not
        deleting) any other an earlier run with other counts gave it."""
        await self.session.execute(
            update(TenantMembership)
            .where(
                TenantMembership.user_id == user_id,
                TenantMembership.tenant_id != tenant_id,
                TenantMembership.deactivated_at.is_(None),
            )
            .values(deactivated_at=func.now())
        )
        await self.session.execute(
            insert(TenantMembership)
            .values(tenant_id=tenant_id, user_id=user_id, role=role)
            .on_conflict_do_update(
                index_elements=[TenantMembership.tenant_id, TenantMembership.user_id],
                set_={"role": role, "deactivated_at": None},
            )
        )
