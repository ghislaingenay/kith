"""FastAPI dependency wiring for the tenants domain."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import container
from core.database import get_session
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
