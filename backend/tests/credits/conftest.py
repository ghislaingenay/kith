"""Fixtures for the credits domain's HTTP tests: the real app and real
Postgres (`db_session`, see tests/conftest.py), with only the caller's
identity replaced."""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_tenant, get_current_user
from auth.schemas import AuthenticatedUser, TenantContext
from credits.dependencies import get_db_session as get_credits_db_session
from main import app
from tenants.dependencies import get_db_session as get_tenants_db_session
from tests.documents.conftest import Caller, make_tenant, make_user


@pytest.fixture
async def caller(db_session: AsyncSession) -> Caller:
    """A Tenant inserted directly, the way one that existed before the
    Credit Ledger looks: no ledger rows at all."""
    return Caller(await make_tenant(db_session), await make_user(db_session))


@pytest.fixture
async def client(
    db_session: AsyncSession, caller: Caller
) -> AsyncIterator[AsyncClient]:
    async def _db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_credits_db_session] = _db_session
    app.dependency_overrides[get_tenants_db_session] = _db_session
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=caller.user_id,
        email="jane@example.com",
        email_verified=True,
        is_active=True,
    )
    app.dependency_overrides[get_current_tenant] = lambda: TenantContext(
        tenant_id=caller.tenant_id, role=caller.role
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()
