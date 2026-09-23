"""Auth-related request context schemas."""

import uuid

from pydantic import BaseModel, EmailStr

from tenants.permissions import Role
from tenants.schemas import TenantMembershipSummary
from users.schemas import ProfileResponse


class AuthenticatedUser(BaseModel):
    id: uuid.UUID
    email: EmailStr
    email_verified: bool
    is_active: bool


class TenantContext(BaseModel):
    tenant_id: uuid.UUID
    role: Role


class MagicLinkRequest(BaseModel):
    email: EmailStr


class MagicLinkRequestResponse(BaseModel):
    message: str


class VerifyMagicLinkResponse(BaseModel):
    message: str


class LogoutResponse(BaseModel):
    message: str


class MeResponse(BaseModel):
    """GET /me: the caller's identity, their Profile and every active Tenant
    Membership — reuses GET /tenants' schema so the frontend redirect logic
    (zero memberships -> onboarding, one -> that tenant) and the app shell
    (name, avatar, Tenant name) have everything they need in a single call."""

    user: AuthenticatedUser
    profile: ProfileResponse
    memberships: list[TenantMembershipSummary]
