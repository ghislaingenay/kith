"""Tenants domain service: tenant data and creation (both the automatic
solo-signup path and the explicit "create another tenant" action)."""

import uuid

from credits.service import CreditsService
from tenants.exceptions import TenantAlreadyExistsError
from tenants.models import TenantMembership
from tenants.repository import TenantsRepository
from tenants.schemas import TenantMembershipSummary


class TenantsService:
    def __init__(
        self, repository: TenantsRepository, credits_service: CreditsService
    ) -> None:
        self.repository = repository
        self.credits_service = credits_service

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
        await self.credits_service.grant_starting_credits(membership.tenant_id)
        await self.repository.commit()
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

    async def activate_pending_memberships(
        self, *, user_id: uuid.UUID, email: str
    ) -> None:
        """Converts every live Pending Membership held by `email` into a
        real TenantMembership. No row is singled out: each is identified by
        its own `tenant_id` and all are closed in one repository call, so it
        doesn't matter how many a person holds or in what order they were
        added."""
        pending = await self.repository.list_pending_memberships(email)
        if not pending:
            return
        await self.repository.activate_pending_memberships(
            user_id=user_id,
            email=email,
            tenant_ids=[row.tenant_id for row in pending],
        )
