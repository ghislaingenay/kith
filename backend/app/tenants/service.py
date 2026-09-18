"""Tenants domain service: tenant data and creation (both the automatic
solo-signup path and the explicit "create another tenant" action)."""

import uuid

from tenants.exceptions import TenantAlreadyExistsError
from tenants.models import TenantMembership
from tenants.repository import TenantsRepository
from tenants.schemas import TenantMembershipSummary


class TenantsService:
    def __init__(self, repository: TenantsRepository) -> None:
        self.repository = repository

    async def provision_default_membership(
        self, *, user_id: uuid.UUID, email: str, first_name: str | None = None
    ) -> TenantMembership:
        return await self.repository.provision_default_membership(
            user_id=user_id, email=email, first_name=first_name
        )

    async def create_tenant(
        self, *, user_id: uuid.UUID, name: str
    ) -> TenantMembershipSummary:
        # Serializes concurrent create_tenant calls for the same user so the
        # "does this user already have a tenant" check below and the insert
        # in repository.create_tenant become atomic — without this, two
        # concurrent requests can both see no existing membership and both
        # succeed, violating the one-tenant-per-user rule this check exists
        # to enforce.
        await self.repository.acquire_user_tenant_lock(user_id)

        rows = await self.repository.list_active_membership_details(user_id)
        if rows:
            raise TenantAlreadyExistsError(name)

        membership, tenant_name, tenant_slug, role = await self.repository.create_tenant(
            user_id=user_id, name=name
        )
        return TenantMembershipSummary(
            tenant_id=membership.tenant_id,
            tenant_name=tenant_name,
            tenant_slug=tenant_slug,
            role=role,
        )

    async def list_my_memberships(
        self, user_id: uuid.UUID
    ) -> list[TenantMembershipSummary]:
        rows = await self.repository.list_active_membership_details(user_id)
        return [
            TenantMembershipSummary(
                tenant_id=membership.tenant_id,
                tenant_name=tenant_name,
                tenant_slug=tenant_slug,
                role=role,
            )
            for membership, tenant_name, tenant_slug, role in rows
        ]
