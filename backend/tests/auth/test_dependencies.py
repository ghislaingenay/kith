"""Unit tests for auth's FastAPI dependency wiring — `get_current_user`
and `get_current_tenant` called directly with fakes, mirroring the
pattern in tests/users/test_dependencies.py and tests/tenants/test_dependencies.py."""

import uuid

import pytest

from auth import dependencies
from auth.exceptions import AuthenticationError
from auth.schemas import AuthenticatedUser, TenantContext
from auth.session import SessionService
from tenants.models import TenantMembership
from tenants.permissions import Role
from tests.support.fake_cache import FakeCacheProvider
from tests.support.fake_db import FakeAsyncSession, FakeResult
from users.models import User


class FakeUserRepository:
    def __init__(self, user: User | None) -> None:
        self._user = user
        self.looked_up: list[str] = []

    async def get_by_user_id(self, user_id: str) -> User | None:
        self.looked_up.append(user_id)
        return self._user


def _user(user_id: uuid.UUID, *, is_active: bool = True) -> User:
    return User(
        id=user_id, email="jane@example.com", email_verified=True, is_active=is_active
    )


class TestGetCurrentUser:
    async def test_raises_when_no_session_cookie_is_sent(self) -> None:
        session_service = SessionService(FakeCacheProvider())

        with pytest.raises(AuthenticationError):
            await dependencies.get_current_user(
                session_service=session_service,
                user_repository=FakeUserRepository(None),
                session_cookie=None,
            )

    async def test_raises_when_the_session_is_unknown_or_expired(self) -> None:
        session_service = SessionService(FakeCacheProvider())

        with pytest.raises(AuthenticationError):
            await dependencies.get_current_user(
                session_service=session_service,
                user_repository=FakeUserRepository(None),
                session_cookie="never-issued",
            )

    async def test_returns_the_authenticated_user_for_a_valid_session(self) -> None:
        cache = FakeCacheProvider()
        session_service = SessionService(cache)
        user_id = uuid.uuid4()
        raw_session_id = await session_service.create_session(user_id)
        user_repository = FakeUserRepository(_user(user_id))

        result = await dependencies.get_current_user(
            session_service=session_service,
            user_repository=user_repository,
            session_cookie=raw_session_id,
        )

        assert result == AuthenticatedUser(
            id=user_id, email="jane@example.com", email_verified=True, is_active=True
        )
        assert user_repository.looked_up == [str(user_id)]

    async def test_raises_when_the_session_points_at_a_deleted_user(self) -> None:
        cache = FakeCacheProvider()
        session_service = SessionService(cache)
        raw_session_id = await session_service.create_session(uuid.uuid4())

        with pytest.raises(AuthenticationError):
            await dependencies.get_current_user(
                session_service=session_service,
                user_repository=FakeUserRepository(None),
                session_cookie=raw_session_id,
            )

    async def test_raises_when_the_user_is_no_longer_active(self) -> None:
        cache = FakeCacheProvider()
        session_service = SessionService(cache)
        user_id = uuid.uuid4()
        raw_session_id = await session_service.create_session(user_id)

        with pytest.raises(AuthenticationError):
            await dependencies.get_current_user(
                session_service=session_service,
                user_repository=FakeUserRepository(_user(user_id, is_active=False)),
                session_cookie=raw_session_id,
            )


_USER = AuthenticatedUser(
    id=uuid.uuid4(), email="jane@example.com", email_verified=True, is_active=True
)


class TestGetCurrentTenant:
    async def test_raises_when_no_x_tenant_id_header_is_sent(self) -> None:
        with pytest.raises(AuthenticationError):
            await dependencies.get_current_tenant(
                user=_USER, session=FakeAsyncSession(), x_tenant_id=None
            )

    async def test_raises_when_x_tenant_id_is_not_a_uuid(self) -> None:
        with pytest.raises(AuthenticationError):
            await dependencies.get_current_tenant(
                user=_USER, session=FakeAsyncSession(), x_tenant_id="not-a-uuid"
            )

    async def test_raises_when_the_caller_has_no_active_membership_there(self) -> None:
        session = FakeAsyncSession(execute_results=[FakeResult(scalar=None)])

        with pytest.raises(AuthenticationError):
            await dependencies.get_current_tenant(
                user=_USER, session=session, x_tenant_id=str(uuid.uuid4())
            )

    async def test_returns_tenant_context_for_an_active_membership(self) -> None:
        tenant_id = uuid.uuid4()
        membership = TenantMembership(
            tenant_id=tenant_id, user_id=_USER.id, role=Role.ADMIN
        )
        session = FakeAsyncSession(execute_results=[FakeResult(scalar=membership)])

        result = await dependencies.get_current_tenant(
            user=_USER, session=session, x_tenant_id=str(tenant_id)
        )

        assert result == TenantContext(tenant_id=tenant_id, role=Role.ADMIN)
