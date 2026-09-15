"""Auth dependencies used by routers."""

from fastapi import Header

from auth.exceptions import AuthenticationError
from auth.schemas import AuthenticatedUser, TenantContext


async def get_current_user() -> AuthenticatedUser:
    raise AuthenticationError("unauthorized")


async def get_current_tenant(x_tenant_id: str | None = Header(default=None)) -> TenantContext:
    if not x_tenant_id:
        raise AuthenticationError("missing tenant context")
    raise AuthenticationError("unauthorized")