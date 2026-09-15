"""Pydantic API schemas for the tenants domain."""

import uuid

from pydantic import BaseModel, Field


class TenantMembershipSummary(BaseModel):
    """One row of an identity's tenant memberships — used by GET /tenants
    and by auth's /me for its memberships list."""

    tenant_id: uuid.UUID
    tenant_name: str
    role_id: uuid.UUID
    role_name: str


class CreateTenantRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class TenantLogoResponse(BaseModel):
    """The tenant's logo URL. `url` is `None` when no logo has been uploaded."""

    url: str | None
