"""HTTP-level tests for the auth router — dependency overrides only,
no DB (mirrors tests/tenants/test_router.py's ASGITransport pattern). Uses
real services wired to fakes (`FakeCacheProvider`/`FakeMailer`/an in-memory
user repository) so behavior is exercised end to end, not mocked away."""

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import MAGIC_LINK_RATE_LIMIT_PER_HOUR, SESSION_COOKIE_NAME
from auth.dependencies import (
    get_current_user,
    get_magic_link_service,
    get_magic_link_verification_service,
    get_session_service,
)
from auth.schemas import AuthenticatedUser
from auth.service import MagicLinkService, MagicLinkVerificationService
from auth.session import SessionService
from core.ratelimit.counter_limiter import CounterLimiter
from core.security import dependencies as security_dependencies
from main import app
from tenants.dependencies import get_tenants_service
from tenants.models import PendingMembership, Tenant, TenantMembership
from tenants.permissions import Role
from tenants.repository import TenantsRepository
from tenants.schemas import TenantMembershipSummary
from tenants.service import TenantsService
from tests.support.fake_cache import FakeCacheProvider
from tests.support.fake_mailer import FakeMailer
from users.models import User
from users.repository import UserRepository

_VERIFY_URL = "http://localhost:8000/api/v1/auth/magic-link/verify"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _override() -> tuple[FakeCacheProvider, FakeMailer]:
    cache = FakeCacheProvider()
    mailer = FakeMailer()
    service = MagicLinkService(
        cache=cache,
        mailer=mailer,
        limiter=CounterLimiter(cache),
        verify_url=_VERIFY_URL,
    )
    app.dependency_overrides[get_magic_link_service] = lambda: service
    return cache, mailer


class TestRequestMagicLink:
    async def test_returns_200_for_a_valid_email(self) -> None:
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/auth/magic-link", json={"email": "jane@example.com"}
            )

        assert response.status_code == 200

    async def test_sends_an_email_for_a_valid_address(self) -> None:
        _, mailer = _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/api/v1/auth/magic-link", json={"email": "jane@example.com"}
            )

        assert len(mailer.sent) == 1
        assert mailer.sent[0]["to"] == "jane@example.com"

    async def test_unknown_email_gets_the_identical_response_as_a_known_one(
        self,
    ) -> None:
        """The service never checks account existence, so "unknown" here
        just means an address with no special-cased handling anywhere —
        same 200, same body shape, an email still goes out."""
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            known_response = await client.post(
                "/api/v1/auth/magic-link", json={"email": "known@example.com"}
            )

        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            unknown_response = await client.post(
                "/api/v1/auth/magic-link", json={"email": "unknown@example.com"}
            )

        assert known_response.status_code == unknown_response.status_code == 200
        assert known_response.json() == unknown_response.json()

    async def test_returns_422_for_a_malformed_email(self) -> None:
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/auth/magic-link", json={"email": "not-an-email"}
            )

        assert response.status_code == 422

    async def test_malformed_email_never_sends_mail(self) -> None:
        _, mailer = _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/api/v1/auth/magic-link", json={"email": "not-an-email"})

        assert mailer.sent == []

    async def test_returns_429_once_the_per_email_rate_limit_is_exceeded(self) -> None:
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(MAGIC_LINK_RATE_LIMIT_PER_HOUR):
                response = await client.post(
                    "/api/v1/auth/magic-link", json={"email": "jane@example.com"}
                )
                assert response.status_code == 200

            response = await client.post(
                "/api/v1/auth/magic-link", json={"email": "jane@example.com"}
            )

        assert response.status_code == 429

    async def test_rate_limit_headers_are_present_on_429(self) -> None:
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(MAGIC_LINK_RATE_LIMIT_PER_HOUR):
                await client.post(
                    "/api/v1/auth/magic-link", json={"email": "jane@example.com"}
                )
            response = await client.post(
                "/api/v1/auth/magic-link", json={"email": "jane@example.com"}
            )

        assert response.headers["X-RateLimit-Limit"] == str(
            MAGIC_LINK_RATE_LIMIT_PER_HOUR
        )
        assert "Retry-After" in response.headers


class FakeUserRepository:
    def __init__(self) -> None:
        self.emails_seen: list[str] = []

    async def get_or_create_user(self, email: str) -> tuple[User, bool]:
        self.emails_seen.append(email)
        return User(id=uuid.uuid4(), email=email, email_verified=False, is_active=True), True


def _seed_token(cache: FakeCacheProvider, *, email: str, token: str) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cache._store[f"magic_link:token:{email.lower()}"] = token_hash


class FakeActivationTenantsService:
    """Stands in for `TenantsService.activate_pending_membership` — records
    calls; DB-backed activation itself is exercised by
    TestVerifyMagicLinkActivatesPendingMembership below and by
    tests/tenants/test_repository.py. (Named distinctly from the
    `FakeTenantsService` below, which stands in for `list_my_memberships`
    for the /me tests — same module, two different fakes.)"""

    def __init__(self) -> None:
        self.activation_calls: list[dict] = []

    async def activate_pending_membership(self, *, user_id, email) -> None:
        self.activation_calls.append({"user_id": user_id, "email": email})


def _override_verify() -> tuple[FakeCacheProvider, FakeUserRepository, SessionService]:
    cache = FakeCacheProvider()
    user_repository = FakeUserRepository()
    session_service = SessionService(cache)
    service = MagicLinkVerificationService(
        cache=cache,
        user_repository=user_repository,
        session_service=session_service,
        tenants_service=FakeActivationTenantsService(),
    )
    app.dependency_overrides[get_magic_link_verification_service] = lambda: service
    return cache, user_repository, session_service


class TestVerifyMagicLink:
    async def test_valid_token_returns_200_creates_a_user_and_sets_a_session_cookie(
        self,
    ) -> None:
        cache, user_repository, session_service = _override_verify()
        _seed_token(cache, email="jane@example.com", token="a-real-token")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/auth/magic-link/verify",
                params={"token": "a-real-token", "email": "jane@example.com"},
            )

        assert response.status_code == 200
        assert user_repository.emails_seen == ["jane@example.com"]

        raw_session_id = response.cookies.get(SESSION_COOKIE_NAME)
        assert raw_session_id is not None
        assert await session_service.resolve_user_id(raw_session_id) is not None

        set_cookie_header = response.headers.get("set-cookie")
        assert set_cookie_header is not None
        assert "httponly" in set_cookie_header.lower()
        assert "samesite=lax" in set_cookie_header.lower()

    async def test_missing_or_expired_token_returns_400(self) -> None:
        _override_verify()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/auth/magic-link/verify",
                params={"token": "never-issued", "email": "jane@example.com"},
            )

        assert response.status_code == 400

    async def test_already_used_token_cannot_be_replayed(self) -> None:
        cache, *_ = _override_verify()
        _seed_token(cache, email="jane@example.com", token="a-real-token")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.get(
                "/api/v1/auth/magic-link/verify",
                params={"token": "a-real-token", "email": "jane@example.com"},
            )
            second = await client.get(
                "/api/v1/auth/magic-link/verify",
                params={"token": "a-real-token", "email": "jane@example.com"},
            )

        assert first.status_code == 200
        assert second.status_code == 400


def _override_logout() -> SessionService:
    cache = FakeCacheProvider()
    session_service = SessionService(cache)
    app.dependency_overrides[get_session_service] = lambda: session_service
    return session_service


class TestLogout:
    async def test_logout_invalidates_the_session_and_clears_the_cookie(self) -> None:
        session_service = _override_logout()
        raw_session_id = await session_service.create_session(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={SESSION_COOKIE_NAME: raw_session_id},
        ) as client:
            response = await client.post("/api/v1/auth/logout")

        assert response.status_code == 200
        assert await session_service.resolve_user_id(raw_session_id) is None
        set_cookie_header = response.headers.get("set-cookie")
        assert set_cookie_header is not None
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie_header

    async def test_logout_without_a_cookie_still_succeeds(self) -> None:
        _override_logout()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/auth/logout")

        assert response.status_code == 200

    async def test_logout_twice_is_not_an_error(self) -> None:
        session_service = _override_logout()
        raw_session_id = await session_service.create_session(uuid.uuid4())

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={SESSION_COOKIE_NAME: raw_session_id},
        ) as client:
            first = await client.post("/api/v1/auth/logout")
            second = await client.post("/api/v1/auth/logout")

        assert first.status_code == 200
        assert second.status_code == 200


class FakeTenantsService:
    def __init__(self) -> None:
        self.memberships: list[TenantMembershipSummary] = []

    async def list_my_memberships(self, user_id):
        return self.memberships


_ME_USER = AuthenticatedUser(
    id=uuid.uuid4(), email="jane@example.com", email_verified=True, is_active=True
)


class TestGetMe:
    async def test_returns_identity_and_memberships_with_no_x_tenant_id_header(
        self,
    ) -> None:
        service = FakeTenantsService()
        service.memberships = [
            TenantMembershipSummary(
                tenant_id=uuid.uuid4(),
                tenant_name="Acme",
                tenant_slug="acme",
                role=Role.OWNER,
            )
        ]
        app.dependency_overrides[get_current_user] = lambda: _ME_USER
        app.dependency_overrides[get_tenants_service] = lambda: service

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 200
        body = response.json()
        assert body["user"]["email"] == "jane@example.com"
        assert len(body["memberships"]) == 1
        assert body["memberships"][0]["tenant_slug"] == "acme"

    async def test_returns_401_when_unauthenticated(self) -> None:
        from auth.exceptions import AuthenticationError

        async def _raise_unauthenticated():
            raise AuthenticationError("unauthorized")

        app.dependency_overrides[get_current_user] = _raise_unauthenticated
        app.dependency_overrides[get_tenants_service] = lambda: FakeTenantsService()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 401


def _mock_container_allowing(allowed_origins: list[str]) -> MagicMock:
    mock_container = MagicMock()
    mock_container.cors_settings.return_value = SimpleNamespace(
        allowed_origins=allowed_origins
    )
    return mock_container


class TestOriginHeaderCheck:
    async def test_disallowed_origin_is_rejected_on_a_state_changing_auth_route(
        self,
    ) -> None:
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            with patch.object(
                security_dependencies,
                "container",
                _mock_container_allowing(["http://localhost:3000"]),
            ):
                response = await client.post(
                    "/api/v1/auth/magic-link",
                    json={"email": "jane@example.com"},
                    headers={"Origin": "http://evil.example.com"},
                )

        assert response.status_code == 403

    async def test_allowed_origin_passes_through(self) -> None:
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            with patch.object(
                security_dependencies,
                "container",
                _mock_container_allowing(["http://localhost:3000"]),
            ):
                response = await client.post(
                    "/api/v1/auth/magic-link",
                    json={"email": "jane@example.com"},
                    headers={"Origin": "http://localhost:3000"},
                )

        assert response.status_code == 200


async def _make_tenant(db_session: AsyncSession, *, name: str = "Acme") -> Tenant:
    tenant = Tenant(
        name=name, slug=f"{name.lower()}-{uuid.uuid4().hex[:8]}", tier="free", max_users=5
    )
    db_session.add(tenant)
    await db_session.commit()
    await db_session.refresh(tenant)
    return tenant


class _EmailDrivenTenantsService:
    """Test-only adapter for these DB-backed tests: MagicLinkVerificationService.verify()
    calls activate_pending_membership(user_id=..., email=...) with no
    tenant_id, but TenantsService.activate_pending_membership now requires
    one explicitly. This resolves the earliest matching PendingMembership
    by email itself, then delegates to the real
    TenantsRepository.activate_pending_membership for the actual DB work,
    so the insert/delete FK behavior under test still runs for real."""

    def __init__(self, repository: TenantsRepository, session: AsyncSession) -> None:
        self._repository = repository
        self._session = session

    async def activate_pending_membership(self, *, user_id: uuid.UUID, email: str) -> None:
        result = await self._session.execute(
            select(PendingMembership)
            .where(PendingMembership.email == email)
            .order_by(PendingMembership.created_at, PendingMembership.tenant_id)
            .limit(1)
        )
        pending = result.scalar_one_or_none()
        if pending is None:
            return
        await self._repository.activate_pending_membership(
            user_id=user_id, tenant_id=pending.tenant_id, email=email
        )


def _override_verify_with_db(db_session: AsyncSession) -> FakeCacheProvider:
    cache = FakeCacheProvider()
    repository = TenantsRepository(db_session)
    service = MagicLinkVerificationService(
        cache=cache,
        user_repository=UserRepository(db_session),
        session_service=SessionService(cache),
        tenants_service=_EmailDrivenTenantsService(repository, db_session),
    )
    app.dependency_overrides[get_magic_link_verification_service] = lambda: service
    return cache


class TestVerifyMagicLinkActivatesPendingMembership:
    """Real Postgres (`db_session`, see tests/conftest.py) — unlike the
    rest of this file, wires MagicLinkVerificationService to real
    UserRepository/TenantsRepository so Pending Membership activation's
    FK-backed insert/delete is exercised end to end through the HTTP
    boundary (issue #12's "router-level tests seed a Pending Membership
    row directly ... and verify activation on sign-in" acceptance
    criterion)."""

    async def test_pending_membership_is_activated_on_first_sign_in(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(
            PendingMembership(
                tenant_id=tenant.id, email="dana@example.com", role=Role.ADMIN
            )
        )
        await db_session.commit()
        cache = _override_verify_with_db(db_session)
        _seed_token(cache, email="dana@example.com", token="a-real-token")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/auth/magic-link/verify",
                params={"token": "a-real-token", "email": "dana@example.com"},
            )

        assert response.status_code == 200

        user = await db_session.scalar(
            select(User).where(User.email == "dana@example.com")
        )
        assert user is not None

        membership = await db_session.scalar(
            select(TenantMembership).where(
                TenantMembership.tenant_id == tenant.id,
                TenantMembership.user_id == user.id,
            )
        )
        assert membership is not None
        assert membership.role == Role.ADMIN

        remaining_pending = await db_session.scalar(
            select(PendingMembership).where(
                PendingMembership.tenant_id == tenant.id,
                PendingMembership.email == "dana@example.com",
            )
        )
        assert remaining_pending is None

    async def test_zero_pending_memberships_falls_through_with_no_membership_created(
        self, db_session: AsyncSession
    ) -> None:
        cache = _override_verify_with_db(db_session)
        _seed_token(cache, email="no-invite@example.com", token="a-real-token")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/auth/magic-link/verify",
                params={"token": "a-real-token", "email": "no-invite@example.com"},
            )

        assert response.status_code == 200

        user = await db_session.scalar(
            select(User).where(User.email == "no-invite@example.com")
        )
        assert user is not None

        membership = await db_session.scalar(
            select(TenantMembership).where(TenantMembership.user_id == user.id)
        )
        assert membership is None

    async def test_only_one_pending_membership_is_activated_when_multiple_match(
        self, db_session: AsyncSession
    ) -> None:
        """This app enforces one active tenant per user and the switcher
        is out of scope this pass (ADR-0008) — so if two Pending
        Memberships match the same email, only one is converted; the other
        stays pending for a future pass."""
        earlier_tenant = await _make_tenant(db_session, name="Earlier")
        later_tenant = await _make_tenant(db_session, name="Later")
        # Explicit, distinct created_at values (rather than the server
        # default, which would give both rows the same transaction
        # timestamp) so this test actually exercises created_at ordering
        # rather than the tenant_id tie-break.
        now = datetime.now(UTC)
        db_session.add_all(
            [
                PendingMembership(
                    tenant_id=later_tenant.id,
                    email="fay@example.com",
                    role=Role.MEMBER,
                    created_at=now + timedelta(seconds=5),
                ),
                PendingMembership(
                    tenant_id=earlier_tenant.id,
                    email="fay@example.com",
                    role=Role.VIEWER,
                    created_at=now,
                ),
            ]
        )
        await db_session.commit()
        cache = _override_verify_with_db(db_session)
        _seed_token(cache, email="fay@example.com", token="a-real-token")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/auth/magic-link/verify",
                params={"token": "a-real-token", "email": "fay@example.com"},
            )

        assert response.status_code == 200

        user = await db_session.scalar(
            select(User).where(User.email == "fay@example.com")
        )
        assert user is not None

        memberships = (
            await db_session.scalars(
                select(TenantMembership).where(TenantMembership.user_id == user.id)
            )
        ).all()
        assert len(memberships) == 1
        assert memberships[0].tenant_id == earlier_tenant.id
        assert memberships[0].role == Role.VIEWER

        remaining_pending = (
            await db_session.scalars(
                select(PendingMembership).where(
                    PendingMembership.email == "fay@example.com"
                )
            )
        ).all()
        assert len(remaining_pending) == 1
        assert remaining_pending[0].tenant_id == later_tenant.id
