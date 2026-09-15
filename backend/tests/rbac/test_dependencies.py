"""Unit tests for rbac's FastAPI dependency wiring.

`get_*_repository` functions are tested by calling them directly with an
explicit session (their `Depends(...)` defaults are FastAPI-only metadata
and never evaluated when the parameter is supplied directly). `get_db_session`
and `get_role_cache_service` go through the module-level `container`, so
those are tested against a mocked stand-in rather than the real container
(which would require live DATABASE_URL/REDIS_URL infrastructure).
"""

from unittest.mock import MagicMock, patch

from rbac import dependencies
from rbac.repository import (
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
)
from tests.support.fake_db import FakeAsyncSession


def test_get_role_repository_wraps_given_session() -> None:
    session = FakeAsyncSession()

    repository = dependencies.get_role_repository(session)

    assert isinstance(repository, RoleRepository)
    assert repository.session is session


def test_get_permission_repository_wraps_given_session() -> None:
    session = FakeAsyncSession()

    repository = dependencies.get_permission_repository(session)

    assert isinstance(repository, PermissionRepository)
    assert repository.session is session


def test_get_role_permission_repository_wraps_given_session() -> None:
    session = FakeAsyncSession()

    repository = dependencies.get_role_permission_repository(session)

    assert isinstance(repository, RolePermissionRepository)
    assert repository.session is session


async def test_get_db_session_yields_session_from_container_factory() -> None:
    fake_session = FakeAsyncSession()

    def fake_session_factory():
        return fake_session

    mock_container = MagicMock()
    mock_container.db_session_factory.return_value = fake_session_factory

    with patch.object(dependencies, "container", mock_container):
        sessions = [session async for session in dependencies.get_db_session()]

    assert sessions == [fake_session]


def test_get_role_cache_service_returns_container_singleton() -> None:
    # RolePermissionCacheService holds process-wide in-memory state (a lock,
    # cached roles/permissions) refreshed on an interval, so this wrapper
    # must return the shared container singleton, never construct a new one.
    sentinel_service = object()
    mock_container = MagicMock()
    mock_container.role_permission_cache_service.return_value = sentinel_service

    with patch.object(dependencies, "container", mock_container):
        result = dependencies.get_role_cache_service()

    assert result is sentinel_service
