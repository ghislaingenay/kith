"""Shared fixtures for domain tests that need a real Postgres (JSONB,
UUID(as_uuid=True), and other dialect-specific behavior plain create_all
against SQLite/fakes can't exercise) or a real Redis (proving actual queue
wiring, not a fake). Backed by throwaway containers (testcontainers),
started once per test session and torn down after — deliberately never the
dev database/Redis (DATABASE_URL/REDIS_URL aren't read here), so a test run
can't touch real data. Skipped entirely when Docker isn't reachable.

Domain-specific `repository` fixtures (AuthRepository, TenantsRepository,
...) stay in each domain's own tests/<domain>/conftest.py — only the
container/session plumbing that's identical across domains lives here.

Also `sentry_events`, shared by every domain that checks what reaches
Sentry (see tests/support/sentry_recorder.py)."""

from collections.abc import AsyncIterator, Iterator

import pytest
from arq.connections import RedisSettings
from core.database import Base, DatabaseSettings, create_engine, create_session_factory
from sentry_sdk.types import Event
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.community.opensearch import OpenSearchContainer
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from tests.support.sentry_recorder import record_sentry_events


@pytest.fixture
def sentry_events() -> Iterator[list[Event]]:
    """Every event Sentry would receive during the test, after scrubbing."""
    with record_sentry_events() as events:
        yield events


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


@pytest.fixture(scope="session")
def _redis_container() -> Iterator[RedisContainer]:
    try:
        with RedisContainer("redis:7-alpine") as redis:
            yield redis
    except Exception as exc:  # noqa: BLE001 — see `_postgres_container` above
        pytest.skip(f"Docker not available — skipping Redis integration tests: {exc}")


@pytest.fixture(scope="session")
def _redis_settings(_redis_container: RedisContainer) -> RedisSettings:
    return RedisSettings(
        host=_redis_container.get_container_host_ip(),
        port=int(_redis_container.get_exposed_port(_redis_container.port)),
    )


@pytest.fixture(scope="session")
def _opensearch_container() -> Iterator[OpenSearchContainer]:
    try:
        with OpenSearchContainer(
            image="opensearchproject/opensearch:2.19.1"
        ) as opensearch:
            yield opensearch
    except Exception as exc:  # noqa: BLE001 — see `_postgres_container` above
        pytest.skip(
            f"Docker not available — skipping OpenSearch integration tests: {exc}"
        )


@pytest.fixture(scope="session")
def _opensearch_url(_opensearch_container: OpenSearchContainer) -> str:
    config = _opensearch_container.get_config()
    return f"http://{config['host']}:{config['port']}"
