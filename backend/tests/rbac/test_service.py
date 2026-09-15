"""Unit tests for `RolePermissionCacheService`.

Uses a fake session factory (tests/support/fake_db.py), stub repositories
(protocol-conforming, in-memory — no SQL), a fake in-memory cache provider
for round-trip behavior (tests/support/fake_cache.py), and
`unittest.mock.AsyncMock` where the point of the test is asserting *how* the
cache provider was called rather than round-trip behavior.
"""

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from core.cache.provider import CacheProvider
from rbac.config import PERMISSIONS_CACHE_KEY, ROLE_CACHE_TTL, ROLES_CACHE_KEY
from rbac.exceptions import CacheLoad
from rbac.models import Permission, Role
from rbac.service import RolePermissionCacheService
from tests.support.fake_cache import FakeCacheProvider
from tests.support.fake_db import FakeAsyncSession

_ADMIN_ROLE_ID = uuid.uuid4()
_VIEWER_ROLE_ID = uuid.uuid4()
_READ_PERMISSION_ID = uuid.uuid4()


def _admin_role() -> Role:
    read_permission = Permission(
        id=_READ_PERMISSION_ID,
        name="users:read",
        resource="users",
        action="read",
        description="Can read users",
    )
    return Role(
        id=_ADMIN_ROLE_ID,
        name="admin",
        display_name="Admin",
        description="Full access",
        is_system_role=True,
        permissions=[read_permission],
    )


def _viewer_role() -> Role:
    return Role(
        id=_VIEWER_ROLE_ID,
        name="viewer",
        display_name="Viewer",
        description="Read-only",
        is_system_role=True,
        permissions=[],
    )


class _StubRoleRepository:
    def __init__(self, roles: list[Role]) -> None:
        self._roles = roles

    async def get_all_roles(self, with_permissions: bool = False) -> list[Role]:
        return self._roles


class _StubPermissionRepository:
    def __init__(self, permissions: list[Permission]) -> None:
        self._permissions = permissions

    async def get_all_permissions(self) -> list[Permission]:
        return self._permissions


class _FailingRoleRepository:
    async def get_all_roles(self, with_permissions: bool = False) -> list[Role]:
        raise ValueError("connection refused")


def _make_service(
    *,
    roles: list[Role] | None = None,
    permissions: list[Permission] | None = None,
    cache_provider: CacheProvider | None = None,
    role_repository_factory=None,
) -> RolePermissionCacheService:
    roles = roles if roles is not None else [_admin_role(), _viewer_role()]
    permissions = permissions if permissions is not None else []

    return RolePermissionCacheService(
        session_factory=lambda: FakeAsyncSession(),
        cache_provider=cache_provider
        if cache_provider is not None
        else FakeCacheProvider(),
        role_repository_factory=role_repository_factory
        or (lambda _session: _StubRoleRepository(roles)),
        permission_repository_factory=lambda _session: _StubPermissionRepository(
            permissions
        ),
    )


async def test_get_role_before_any_refresh_returns_miss_not_error() -> None:
    # Regression: the service used to initialize `_roles_by_name`/`_roles_by_id`
    # in __init__ but read `_by_name`/`_by_id` in get_role/get_role_by_id —
    # an AttributeError on first call, before refresh() ever ran.
    service = _make_service()

    role, found = await service.get_role("admin")

    assert role is None
    assert found is False


async def test_refresh_populates_in_memory_lookups() -> None:
    service = _make_service()

    await service.refresh()

    role, found = await service.get_role("admin")
    assert found is True
    assert role.name == "admin"
    assert role.permissions == ["users:read"]

    role_by_id, found_by_id = await service.get_role_by_id(_ADMIN_ROLE_ID)
    assert found_by_id is True
    assert role_by_id.id == str(_ADMIN_ROLE_ID)

    assert {r.name for r in await service.all()} == {"admin", "viewer"}


async def test_refresh_wraps_repository_errors_in_cache_load() -> None:
    # Regression: CacheLoad.__init__ took no args, so `raise CacheLoad(f"...")`
    # itself raised TypeError instead of the intended domain exception.
    service = _make_service(role_repository_factory=lambda _s: _FailingRoleRepository())

    with pytest.raises(CacheLoad) as exc_info:
        await service.refresh()

    assert "connection refused" in str(exc_info.value)


async def test_refresh_writes_through_to_cache_with_ttl_as_positional_arg() -> None:
    # Regression: `_write_through` called `cache_provider.set(key, value, ex=ttl)`
    # but `CacheProvider.set`'s third parameter is positional `ttl_seconds`,
    # not a keyword named `ex` — every write-through call raised TypeError.
    mock_cache = AsyncMock(spec=CacheProvider)
    service = _make_service(cache_provider=mock_cache)

    await service.refresh()

    expected_ttl = int(ROLE_CACHE_TTL.total_seconds())
    assert mock_cache.set.await_count == 2
    for call in mock_cache.set.await_args_list:
        args, kwargs = call
        assert kwargs == {}
        key, value, ttl_seconds = args
        assert key in (ROLES_CACHE_KEY, PERMISSIONS_CACHE_KEY)
        assert ttl_seconds == expected_ttl
        json.loads(
            value
        )  # must be valid, serializable JSON — not a bare pydantic model


async def test_cache_round_trip_yields_same_outcome_as_fresh_db_load() -> None:
    # The instruction this addresses: after refresh(), reading roles back
    # from the cache must produce the same data as loading from the DB.
    fake_cache = FakeCacheProvider()
    service = _make_service(cache_provider=fake_cache)
    await service.refresh()
    role_from_db_backed_state, _ = await service.get_role("admin")

    (
        roles_from_cache,
        permissions_from_cache,
        loaded_from_cache,
    ) = await service._try_load_from_redis()

    assert loaded_from_cache is True
    assert [r.name for r in roles_from_cache] == ["admin", "viewer"]
    admin_from_cache = next(r for r in roles_from_cache if r.name == "admin")
    assert admin_from_cache == role_from_db_backed_state
    assert permissions_from_cache == []


async def test_try_load_from_redis_returns_miss_when_absent() -> None:
    service = _make_service(cache_provider=FakeCacheProvider())

    roles, permissions, loaded_from_cache = await service._try_load_from_redis()

    assert roles == []
    assert permissions == []
    assert loaded_from_cache is False


async def test_all_permissions_returns_loaded_permissions() -> None:
    read_permission = Permission(
        id=_READ_PERMISSION_ID,
        name="users:read",
        resource="users",
        action="read",
        description="Can read users",
    )
    service = _make_service(roles=[], permissions=[read_permission])

    await service.refresh()

    permissions = await service.all_permissions()
    assert [p.name for p in permissions] == ["users:read"]
