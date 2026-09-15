"""Unit tests for the rbac repositories against a fake `AsyncSession` — no
real database needed, mirroring this project's convention of testing
adapter/repository logic against a fake/mocked client rather than live
infrastructure (see tests/core/cache/test_redis_provider.py).
"""

import uuid

from rbac.models import Permission, Role
from rbac.repository import (
    PermissionRepository,
    RolePermissionRepository,
    RoleRepository,
)
from tests.support.fake_db import FakeAsyncSession, FakeResult

_ROLE_ID = uuid.uuid4()
_PERMISSION_ID = uuid.uuid4()


def _make_role(name: str = "admin") -> Role:
    return Role(
        id=_ROLE_ID,
        name=name,
        display_name=name.title(),
        description="A role",
        is_system_role=True,
    )


def _make_permission(name: str = "users:read") -> Permission:
    return Permission(
        id=_PERMISSION_ID,
        name=name,
        resource="users",
        action="read",
        description="Can read users",
    )


async def test_get_role_by_name_returns_role() -> None:
    role = _make_role()
    session = FakeAsyncSession(execute_results=[FakeResult(scalars_list=[role])])
    repository = RoleRepository(session)

    result = await repository.get_role_by_name("admin")

    assert result is role


async def test_get_role_by_name_returns_none_when_absent() -> None:
    session = FakeAsyncSession(execute_results=[FakeResult(scalars_list=[])])
    repository = RoleRepository(session)

    result = await repository.get_role_by_name("missing")

    assert result is None


async def test_get_all_roles_orders_by_name() -> None:
    session = FakeAsyncSession(execute_results=[FakeResult(scalars_list=[])])
    repository = RoleRepository(session)

    await repository.get_all_roles()

    compiled = str(session.executed_statements[0])
    assert "ORDER BY roles.name" in compiled


async def test_get_all_permissions_orders_by_resource_and_action() -> None:
    session = FakeAsyncSession(execute_results=[FakeResult(scalars_list=[])])
    repository = PermissionRepository(session)

    await repository.get_all_permissions()

    compiled = str(session.executed_statements[0])
    assert "ORDER BY permissions.resource, permissions.action" in compiled


async def test_get_permission_by_name_returns_permission() -> None:
    permission = _make_permission()
    session = FakeAsyncSession(execute_results=[FakeResult(scalars_list=[permission])])
    repository = PermissionRepository(session)

    result = await repository.get_permission_by_name("users:read")

    assert result is permission


async def test_get_permission_names_by_role_groups_by_role_id() -> None:
    role_a, role_b = uuid.uuid4(), uuid.uuid4()
    rows = [
        (role_a, "users:read"),
        (role_a, "users:update"),
        (role_b, "tenants:read"),
    ]
    session = FakeAsyncSession(execute_results=[FakeResult(rows=rows)])
    repository = RolePermissionRepository(session)

    by_role = await repository.get_permission_names_by_role()

    assert by_role[role_a] == ["users:read", "users:update"]
    assert by_role[role_b] == ["tenants:read"]
