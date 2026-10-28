"""Tests for `make load-test-sessions` (#160): the operator creates Load Test
Tenants, their Users and one Session per User for k6. The command is called
as a function against real Postgres and Redis, and what it made is read back
through the HTTP API with the returned Session id as the session cookie."""

import logging
import os
import subprocess
import sys
from collections import Counter
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from arq.connections import RedisSettings
from auth.config import SESSION_COOKIE_NAME
from auth.dependencies import get_cache_provider
from auth.dependencies import get_db_session as auth_get_db_session
from core.cache.redis_provider import RedisCacheProvider
from core.database import DatabaseSettings, create_engine, create_session_factory
from core.storage.dependencies import get_storage_provider
from credits.dependencies import get_db_session as credits_get_db_session
from credits.models import CreditLedgerEntry, CreditLedgerKind
from httpx import ASGITransport, AsyncClient
from loadtest.config import LoadTestSettings
from loadtest.exceptions import (
    InvalidLoadTestSizeError,
    LoadTestDisabledError,
    NonReservedEmailDomainError,
)
from loadtest.sessions import LoadTestSession, create_load_test_sessions
from main import app
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tenants.dependencies import get_db_session as tenants_get_db_session
from tenants.models import Tenant
from users.dependencies import get_db_session as users_get_db_session
from users.models import User

from tests.support.fake_storage import FakeStorageProvider

_ENABLED = LoadTestSettings(enabled=True)


@pytest.fixture
async def session_factory(
    db_session: AsyncSession, _database_url: str
) -> AsyncIterator[async_sessionmaker]:
    # Depends on `db_session` only so its tables exist before the command runs.
    engine = create_engine(DatabaseSettings(database_url=_database_url))
    yield create_session_factory(engine)
    await engine.dispose()


@pytest.fixture
async def cache(_redis_settings: RedisSettings) -> AsyncIterator[RedisCacheProvider]:
    provider = RedisCacheProvider(
        redis_url=f"redis://{_redis_settings.host}:{_redis_settings.port}/0"
    )
    yield provider
    await provider.close()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker, cache: RedisCacheProvider
) -> AsyncIterator[AsyncClient]:
    """The real app with real Postgres and Redis; only storage is faked.
    Nothing about who is calling is replaced: the session cookie decides."""

    async def _db_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    for get_db_session in (
        auth_get_db_session,
        users_get_db_session,
        tenants_get_db_session,
        credits_get_db_session,
    ):
        app.dependency_overrides[get_db_session] = _db_session
    app.dependency_overrides[get_cache_provider] = lambda: cache
    app.dependency_overrides[get_storage_provider] = FakeStorageProvider
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()


async def _create(
    session_factory: async_sessionmaker,
    cache: RedisCacheProvider,
    *,
    tenants: int = 2,
    users: int = 4,
    credits: int = 1_000,
    settings: LoadTestSettings = _ENABLED,
    email_domain: str | None = None,
) -> list[LoadTestSession]:
    extra = {} if email_domain is None else {"email_domain": email_domain}
    return await create_load_test_sessions(
        session_factory,
        cache,
        settings,
        tenants=tenants,
        users=users,
        credits=credits,
        **extra,
    )


async def _get(client: AsyncClient, url: str, session: LoadTestSession) -> dict:
    response = await client.get(
        url,
        cookies={SESSION_COOKIE_NAME: session.session_id},
        headers={"X-Tenant-ID": str(session.tenant_id)},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _count(db_session: AsyncSession, model: type) -> int:
    return await db_session.scalar(select(func.count()).select_from(model))


async def test_a_returned_session_id_signs_in_as_the_load_test_user(
    client: AsyncClient, session_factory: async_sessionmaker, cache: RedisCacheProvider
) -> None:
    sessions = await _create(session_factory, cache)

    for session in sessions:
        me = await _get(client, "/api/v1/me", session)
        assert me["user"]["id"] == str(session.user_id)
        assert me["user"]["email"] == session.email
        assert session.email.endswith("@loadtest.example")


async def test_each_user_belongs_to_exactly_one_load_test_tenant(
    client: AsyncClient, session_factory: async_sessionmaker, cache: RedisCacheProvider
) -> None:
    sessions = await _create(session_factory, cache, tenants=3, users=7)

    for session in sessions:
        memberships = (await _get(client, "/api/v1/me", session))["memberships"]
        assert [m["tenant_id"] for m in memberships] == [str(session.tenant_id)]


async def test_users_are_spread_evenly_across_tenants(
    session_factory: async_sessionmaker, cache: RedisCacheProvider
) -> None:
    sessions = await _create(session_factory, cache, tenants=3, users=7)

    per_tenant = Counter(session.tenant_id for session in sessions)
    assert len(sessions) == 7
    assert len({session.user_id for session in sessions}) == 7
    assert sorted(per_tenant.values()) == [2, 2, 3]


async def test_each_tenant_shows_the_grant_as_a_credit_adjustment_with_a_note(
    client: AsyncClient,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    cache: RedisCacheProvider,
) -> None:
    sessions = await _create(session_factory, cache, credits=5_000)

    for tenant_id, session in {s.tenant_id: s for s in sessions}.items():
        balance = await _get(client, "/api/v1/credit-balance", session)
        assert balance["credits"] == 5_000
        rows = (
            await db_session.scalars(
                select(CreditLedgerEntry).where(
                    CreditLedgerEntry.tenant_id == tenant_id
                )
            )
        ).all()
        assert [(row.kind, bool(row.note.strip())) for row in rows] == [
            (CreditLedgerKind.ADJUSTMENT, True)
        ]


async def test_a_second_run_creates_no_duplicates_and_issues_fresh_sessions(
    client: AsyncClient,
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    cache: RedisCacheProvider,
) -> None:
    first = await _create(session_factory, cache, tenants=2, users=4)
    tenants_after_first = await _count(db_session, Tenant)
    users_after_first = await _count(db_session, User)

    second = await _create(session_factory, cache, tenants=2, users=4)

    assert await _count(db_session, Tenant) == tenants_after_first == 2
    assert await _count(db_session, User) == users_after_first == 4
    assert [(s.user_id, s.tenant_id) for s in second] == [
        (s.user_id, s.tenant_id) for s in first
    ]
    assert {s.session_id for s in second}.isdisjoint(s.session_id for s in first)
    for session in second:
        me = await _get(client, "/api/v1/me", session)
        assert len(me["memberships"]) == 1


async def test_a_second_run_tops_the_balance_back_up_rather_than_adding_to_it(
    client: AsyncClient, session_factory: async_sessionmaker, cache: RedisCacheProvider
) -> None:
    await _create(session_factory, cache, credits=1_000)

    sessions = await _create(session_factory, cache, credits=1_000)

    for session in sessions:
        balance = await _get(client, "/api/v1/credit-balance", session)
        assert balance["credits"] == 1_000


async def test_a_rerun_with_fewer_tenants_leaves_each_user_one_live_membership(
    client: AsyncClient, session_factory: async_sessionmaker, cache: RedisCacheProvider
) -> None:
    await _create(session_factory, cache, tenants=2, users=4)

    sessions = await _create(session_factory, cache, tenants=1, users=4)

    for session in sessions:
        memberships = (await _get(client, "/api/v1/me", session))["memberships"]
        assert [m["tenant_id"] for m in memberships] == [str(session.tenant_id)]


@pytest.mark.parametrize(
    "size", [{"tenants": 0}, {"users": 0}, {"credits": 0}, {"tenants": -1}]
)
async def test_a_count_below_one_is_refused_and_nothing_is_written(
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    cache: RedisCacheProvider,
    size: dict[str, int],
) -> None:
    with pytest.raises(InvalidLoadTestSizeError):
        await _create(session_factory, cache, **size)

    assert await _count(db_session, Tenant) == 0
    assert await _count(db_session, User) == 0


async def test_it_refuses_to_run_without_the_load_test_flag_and_writes_nothing(
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    cache: RedisCacheProvider,
) -> None:
    with pytest.raises(LoadTestDisabledError):
        await _create(session_factory, cache, settings=LoadTestSettings(enabled=False))

    assert await _count(db_session, Tenant) == 0
    assert await _count(db_session, User) == 0


def test_the_flag_is_off_unless_the_environment_turns_it_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LOAD_TEST_ENABLED", raising=False)
    assert LoadTestSettings().enabled is False

    monkeypatch.setenv("LOAD_TEST_ENABLED", "true")
    assert LoadTestSettings().enabled is True


@pytest.mark.parametrize(
    "domain", ["example.com", "kith.app", "loadtest.example.com", "loadtest.invalid"]
)
async def test_it_refuses_any_email_outside_the_reserved_domain_and_writes_nothing(
    db_session: AsyncSession,
    session_factory: async_sessionmaker,
    cache: RedisCacheProvider,
    domain: str,
) -> None:
    with pytest.raises(NonReservedEmailDomainError):
        await _create(session_factory, cache, email_domain=domain)

    assert await _count(db_session, Tenant) == 0
    assert await _count(db_session, User) == 0


async def test_session_ids_never_appear_in_logs(
    session_factory: async_sessionmaker,
    cache: RedisCacheProvider,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    caplog.set_level(logging.DEBUG)

    sessions = await _create(session_factory, cache)

    output = caplog.text + "".join(capsys.readouterr())
    for session in sessions:
        assert session.session_id not in output
        assert session.session_id not in repr(session)


def test_the_script_alone_knows_every_table_it_writes_to() -> None:
    # A fresh interpreter: this process's imports would hide a missing table.
    check = (
        "import scripts.load_test_sessions\n"
        "from core.database import Base\n"
        "for table in Base.metadata.tables.values():\n"
        "    for fk in table.foreign_keys:\n"
        "        if table.name in {'credit_ledger', 'tenant_memberships', 'profiles'}:\n"
        "            fk.column\n"
    )
    app_dir = Path(__file__).resolve().parents[2] / "app"

    result = subprocess.run(
        [sys.executable, "-c", check],
        env={**os.environ, "PYTHONPATH": str(app_dir)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
