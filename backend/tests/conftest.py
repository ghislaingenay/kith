"""Shared fixtures for domain tests that need a real Postgres (JSONB,
UUID(as_uuid=True), and other dialect-specific behavior plain create_all
against SQLite/fakes can't exercise). Backed by a throwaway Postgres
container (testcontainers), started once per test session and torn down
after — deliberately never the dev database (DATABASE_URL isn't read here),
so a test run can't wipe real data. Skipped entirely when Docker isn't
reachable.

Domain-specific `repository` fixtures (AuthRepository, TenantsRepository,
...) stay in each domain's own tests/<domain>/conftest.py — only the
container/session plumbing that's identical across domains lives here."""

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.postgres import PostgresContainer

from core.database import Base, DatabaseSettings, create_engine, create_session_factory
from rbac.models import Role


@pytest.fixture(scope="session")
def _postgres_container() -> Iterator[PostgresContainer]:
    try:
        with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
            yield postgres
    except Exception as exc:  # noqa: BLE001 — testcontainers raises whatever
        # the docker SDK gives it (docker.errors.DockerException and
        # friends); any of them means "no usable Docker here", so skip.
        pytest.skip(
            f"Docker not available — skipping Postgres integration tests: {exc}"
        )


@pytest.fixture(scope="session")
def _database_url(_postgres_container: PostgresContainer) -> str:
    return _postgres_container.get_connection_url()


@pytest.fixture
async def db_session(_database_url: str) -> AsyncIterator[AsyncSession]:
    settings = DatabaseSettings(database_url=_database_url)
    engine = create_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
async def owner_role(db_session: AsyncSession) -> Role:
    role = Role(
        id=uuid.uuid4(),
        name="owner",
        display_name="Owner",
        description="Full access within their own tenant.",
        is_system_role=True,
    )
    db_session.add(role)
    await db_session.commit()
    return role
