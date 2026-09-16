"""Domain-specific fixtures for tenants repository tests. The Postgres
container/session fixture (`db_session`) is shared across domains — see
tests/conftest.py."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tenants.repository import TenantsRepository


@pytest.fixture
def repository(db_session: AsyncSession) -> TenantsRepository:
    return TenantsRepository(db_session)
