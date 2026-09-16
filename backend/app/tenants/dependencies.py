"""FastAPI dependency wiring for the tenants domain."""

from collections.abc import AsyncIterator, Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_tenant
from auth.schemas import TenantContext
from core.container import container
from core.database import get_session
from tenants.exceptions import PermissionDenied
from tenants.permissions import Action, has_permission
from tenants.repository import TenantsRepository
from tenants.service import TenantsService


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session(container.db_session_factory()):
        yield session


def get_tenant_repository(
    session: AsyncSession = Depends(get_db_session),
) -> TenantsRepository:
    return TenantsRepository(session)


def get_tenants_service(
    tenant_repository: Annotated[TenantsRepository, Depends(get_tenant_repository)],
) -> TenantsService:
    return TenantsService(tenant_repository)


def require_permission(
    action: Action,
) -> Callable[[TenantContext], Coroutine[Any, Any, None]]:
    """Return a FastAPI dependency that raises `PermissionDenied` unless the
    current tenant context's Role may perform `action` (see ADR-0007).
    Routers declare it alongside `get_current_tenant`, e.g.
    `Depends(require_permission(Action.SETTINGS))` — never a hand-written
    Role comparison."""

    async def _require_permission(
        tenant: Annotated[TenantContext, Depends(get_current_tenant)],
    ) -> None:
        if not has_permission(tenant.role, action):
            raise PermissionDenied(action)

    return _require_permission
