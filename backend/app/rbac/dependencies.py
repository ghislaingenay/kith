"""FastAPI dependency wiring for the rbac domain."""

from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import container
from core.database import get_session
from rbac.repository import (
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
)
from rbac.service import RolePermissionCacheService


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session(container.db_session_factory()):
        yield session


def get_role_repository(
    session: AsyncSession = Depends(get_db_session),
) -> RoleRepository:
    return RoleRepository(session)


def get_permission_repository(
    session: AsyncSession = Depends(get_db_session),
) -> PermissionRepository:
    return PermissionRepository(session)


def get_role_permission_repository(
    session: AsyncSession = Depends(get_db_session),
) -> RolePermissionRepository:
    return RolePermissionRepository(session)


def get_role_cache_service() -> RolePermissionCacheService:
    # `RolePermissionCacheService` holds process-wide in-memory state (the
    # cached roles/permissions and their lock) refreshed on an interval —
    # it's a container singleton, not a per-request object, so this wrapper
    # returns the shared instance instead of constructing a new one.
    return container.role_permission_cache_service()
