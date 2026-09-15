"""Auth-related request context schemas."""

import uuid

from pydantic import BaseModel, EmailStr


class AuthenticatedUser(BaseModel):
    id: uuid.UUID
    email: EmailStr
    email_verified: bool
    is_active: bool


class TenantContext(BaseModel):
    tenant_id: uuid.UUID
    role_id: uuid.UUID