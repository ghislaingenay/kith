"""HTTP-level tests for the auth router — dependency overrides only,
no DB (mirrors tests/tenants/test_router.py's ASGITransport pattern). Uses
real services wired to fakes (`FakeCacheProvider`/`FakeMailer`/an in-memory
user repository) so behavior is exercised end to end, not mocked away."""

import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from arq.connections import RedisSettings
from httpx import ASGITransport, AsyncClient, Response
from redis import asyncio as redis_asyncio
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
from auth.config import MAGIC_LINK_IP_RATE_LIMIT_PER_HOUR
from core.ratelimit.counter_limiter import CounterLimiter
from core.ratelimit.dependencies import get_rate_limiter
from core.ratelimit.limiter import SlidingWindowLimiter
from core.security import dependencies as security_dependencies
from credits.config import CreditSettings
from credits.repository import CreditsRepository
from credits.service import CreditsService
from main import app
from tenants.dependencies import get_tenants_service
from tenants.models import (
    PendingMembership,
    PendingMembershipStatus,
    Tenant,
    TenantMembership,
)
from tenants.permissions import Role
from tenants.repository import TenantsRepository
from tenants.schemas import TenantMembershipSummary
from tenants.service import TenantsService
from tests.support.fake_cache import FakeCacheProvider
from tests.support.fake_mailer import FakeMailer
from tests.support.fake_storage import FakeStorageProvider, RaisingStorageProvider
from users.dependencies import (
    get_db_session as users_get_db_session,
)
from users.dependencies import get_profile_service, get_user_repository
from users.models import Profile, User
from users.repository import ProfileRepository, UserRepository
from users.service import ProfileService

_VERIFY_URL = "http://localhost:8000/api/v1/auth/magic-link/verify"
_MAGIC_LINKS_PER_IP_PER_HOUR = MAGIC_LINK_IP_RATE_LIMIT_PER_HOUR
# Caddy's `X-Forwarded-For`: the real peer, replacing the client's (ADR-0020).
_OFFICE_IP = "203.0.113.7"
_OTHER_IP = "198.51.100.23"


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
async def _rate_limiter(_redis_settings: RedisSettings) -> AsyncIterator[None]:
    """The real Redis sliding-window limiter, emptied per test, behind the
    per-IP limit on Magic Link requests."""
    redis_client = redis_asyncio.Redis(
        host=_redis_settings.host,
        port=_redis_settings.port,
        decode_responses=True,
    )
    await redis_client.flushall()
    app.dependency_overrides[get_rate_limiter] = lambda: SlidingWindowLimiter(
        redis_client
    )
    yield
    await redis_client.aclose()


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


async def _request_magic_link(
    client: AsyncClient, email: str, ip: str, headers: dict[str, str] | None = None
) -> Response:
    return await client.post(
        "/api/v1/auth/magic-link",
        json={"email": email},
        headers={"X-Forwarded-For": ip, **(headers or {})},
    )


class TestRequestMagicLinkPerIPLimit:
    async def test_the_21st_request_from_one_ip_in_an_hour_gets_429(self) -> None:
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            statuses = [
                (
                    await _request_magic_link(
                        client, f"user{i}@example.com", _OFFICE_IP
                    )
                ).status_code
                for i in range(_MAGIC_LINKS_PER_IP_PER_HOUR)
            ]
            response = await _request_magic_link(
                client, "one-more@example.com", _OFFICE_IP
            )

        assert statuses == [200] * _MAGIC_LINKS_PER_IP_PER_HOUR
        assert response.status_code == 429
        assert response.headers["X-RateLimit-Limit"] == str(
            _MAGIC_LINKS_PER_IP_PER_HOUR
        )
        assert response.headers["X-RateLimit-Remaining"] == "0"
        assert int(response.headers["Retry-After"]) > 0

    async def test_the_limited_ip_sends_no_more_emails(self) -> None:
        _, mailer = _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for i in range(_MAGIC_LINKS_PER_IP_PER_HOUR + 5):
                await _request_magic_link(client, f"user{i}@example.com", _OFFICE_IP)

        assert len(mailer.sent) == _MAGIC_LINKS_PER_IP_PER_HOUR

    async def test_a_different_ip_still_succeeds_once_one_ip_is_limited(
        self,
    ) -> None:
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for i in range(_MAGIC_LINKS_PER_IP_PER_HOUR + 1):
                await _request_magic_link(client, f"user{i}@example.com", _OFFICE_IP)
            response = await _request_magic_link(
                client, "colleague@example.com", _OTHER_IP
            )

        assert response.status_code == 200

    async def test_a_client_sent_x_real_ip_cannot_dodge_the_ip_caddy_forwarded(
        self,
    ) -> None:
        """Caddy passes a client's `X-Real-IP` through untouched, unlike
        `X-Forwarded-For`, so it must never decide the IP."""
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            statuses = [
                (
                    await _request_magic_link(
                        client,
                        f"user{i}@example.com",
                        _OFFICE_IP,
                        headers={"X-Real-IP": f"10.0.0.{i}"},
                    )
                ).status_code
                for i in range(_MAGIC_LINKS_PER_IP_PER_HOUR + 1)
            ]

        assert statuses[-1] == 429

    async def test_the_per_email_limit_still_applies_across_ips(self) -> None:
        _override()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            statuses = [
                (
                    await _request_magic_link(
                        client, "jane@example.com", f"203.0.113.{i}"
                    )
                ).status_code
                for i in range(MAGIC_LINK_RATE_LIMIT_PER_HOUR + 1)
            ]

        assert statuses == [200] * MAGIC_LINK_RATE_LIMIT_PER_HOUR + [429]

    async def test_magic_link_verification_is_not_limited_per_ip(self) -> None:
        _override_verify()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            statuses = {
                (
                    await client.get(
                        "/api/v1/auth/magic-link/verify",
                        params={"token": "never-issued", "email": "jane@example.com"},
                        headers={"X-Forwarded-For": _OFFICE_IP},
                    )
                ).status_code
                for _ in range(_MAGIC_LINKS_PER_IP_PER_HOUR + 1)
            }

        assert statuses == {400}


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
    """Stands in for `TenantsService.activate_pending_memberships` — records
    calls; DB-backed activation itself is exercised by
    TestVerifyMagicLinkActivatesPendingMembership below and by
    tests/tenants/test_repository.py. (Named distinctly from the
    `FakeTenantsService` below, which stands in for `list_my_memberships`
    for the /me tests — same module, two different fakes.)"""

    def __init__(self) -> None:
        self.activation_calls: list[dict] = []

    async def activate_pending_memberships(self, *, user_id, email) -> None:
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


class FakeProfilelessUserRepository:
    """Returns a stored user that has no Profile row."""

    async def get_by_user_id(self, user_id, *, with_profile=False):
        return SimpleNamespace(profile=None)


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
        app.dependency_overrides[get_user_repository] = (
            lambda: FakeProfilelessUserRepository()
        )
        app.dependency_overrides[get_profile_service] = lambda: ProfileService(
            None, FakeStorageProvider()  # type: ignore[arg-type]
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 200
        body = response.json()
        assert body["user"]["email"] == "jane@example.com"
        assert len(body["memberships"]) == 1
        assert body["memberships"][0]["tenant_slug"] == "acme"
        assert body["profile"]["email"] == "jane@example.com"

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


class TestGetMeProfile:
    """Real Postgres (`db_session`): `/me` loads the Profile together with the
    User (one `selectinload`), which fakes can't prove works against the
    `users`/`profiles` mapping."""

    async def _get_me(
        self,
        db_session: AsyncSession,
        user: User,
        storage: FakeStorageProvider | None = None,
    ) -> dict:
        auth_user = AuthenticatedUser(
            id=user.id, email=user.email, email_verified=True, is_active=True
        )
        app.dependency_overrides[get_current_user] = lambda: auth_user
        app.dependency_overrides[get_tenants_service] = lambda: FakeTenantsService()
        app.dependency_overrides[get_user_repository] = lambda: UserRepository(
            db_session
        )
        app.dependency_overrides[get_profile_service] = lambda: ProfileService(
            ProfileRepository(db_session), storage or FakeStorageProvider()
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 200
        return response.json()

    async def test_returns_email_only_profile_when_the_user_has_no_profile(
        self, db_session: AsyncSession
    ) -> None:
        user = User(email="pia@example.com")
        db_session.add(user)
        await db_session.commit()

        body = await self._get_me(db_session, user)

        assert body["profile"] == {
            "email": "pia@example.com",
            "name": None,
            "avatar_url": None,
        }

    async def test_returns_name_and_presigned_avatar_url_from_the_profile(
        self, db_session: AsyncSession
    ) -> None:
        user = User(email="quinn@example.com")
        db_session.add(user)
        await db_session.commit()
        key = f"user/{user.id}/avatar/avatar.png"
        db_session.add(Profile(user_id=user.id, first_name="Quinn", avatar_url=key))
        await db_session.commit()

        body = await self._get_me(db_session, user)

        assert body["profile"] == {
            "email": "quinn@example.com",
            "name": "Quinn",
            "avatar_url": f"https://cdn.example.com/{key}?signature=fake&method=GET",
        }

    async def test_signing_in_still_succeeds_when_avatar_presigning_fails(
        self, db_session: AsyncSession
    ) -> None:
        """`/me` sits on the sign-in redirect path (see
        verify-and-redirect.ts) — a storage outage must not block sign-in."""
        user = User(email="uma@example.com")
        db_session.add(user)
        await db_session.commit()
        key = f"user/{user.id}/avatar/avatar.png"
        db_session.add(Profile(user_id=user.id, first_name="Uma", avatar_url=key))
        await db_session.commit()

        body = await self._get_me(db_session, user, RaisingStorageProvider())

        assert body["profile"] == {
            "email": "uma@example.com",
            "name": "Uma",
            "avatar_url": None,
        }


class TestGetMeProfileThroughRealSession:
    """`get_current_user` and `/me` share one request-scoped session, so `/me`
    re-queries a User that is already in the identity map without its Profile
    — the case a test that overrides `get_current_user` never reaches."""

    async def test_loads_the_profile_of_a_user_the_session_dependency_already_loaded(
        self, db_session: AsyncSession
    ) -> None:
        user = User(email="rae@example.com")
        db_session.add(user)
        await db_session.commit()
        key = f"user/{user.id}/avatar/avatar.png"
        db_session.add(Profile(user_id=user.id, first_name="Rae", avatar_url=key))
        await db_session.commit()
        db_session.expunge_all()

        cache = FakeCacheProvider()
        session_service = SessionService(cache)
        raw_session_id = await session_service.create_session(user.id)
        app.dependency_overrides[get_session_service] = lambda: session_service
        app.dependency_overrides[users_get_db_session] = lambda: db_session
        app.dependency_overrides[get_tenants_service] = lambda: FakeTenantsService()
        app.dependency_overrides[get_profile_service] = lambda: ProfileService(
            ProfileRepository(db_session), FakeStorageProvider()
        )

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={SESSION_COOKIE_NAME: raw_session_id},
        ) as client:
            response = await client.get("/api/v1/me")

        assert response.status_code == 200
        assert response.json()["profile"] == {
            "email": "rae@example.com",
            "name": "Rae",
            "avatar_url": f"https://cdn.example.com/{key}?signature=fake&method=GET",
        }
        stored = await db_session.scalar(select(Profile).where(Profile.user_id == user.id))
        assert stored is not None and stored.avatar_url == key


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


def _override_verify_with_db(db_session: AsyncSession) -> FakeCacheProvider:
    cache = FakeCacheProvider()
    repository = TenantsRepository(db_session)
    service = MagicLinkVerificationService(
        cache=cache,
        user_repository=UserRepository(db_session),
        session_service=SessionService(cache),
        tenants_service=TenantsService(
            repository, CreditsService(CreditsRepository(db_session), CreditSettings())
        ),
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

        closed = await db_session.scalar(
            select(PendingMembership)
            .where(
                PendingMembership.tenant_id == tenant.id,
                PendingMembership.email == "dana@example.com",
            )
            .execution_options(populate_existing=True)
        )
        assert closed is not None
        assert closed.status == PendingMembershipStatus.ACCEPTED

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

    async def test_every_matching_pending_membership_is_activated(
        self, db_session: AsyncSession
    ) -> None:
        """Each Pending Membership is its own row with its own tenant_id, so
        none is singled out; which Tenant the person lands in afterwards is
        /me's stable (created_at, tenant_id) ordering, not an activation
        decision."""
        first_tenant = await _make_tenant(db_session, name="First")
        second_tenant = await _make_tenant(db_session, name="Second")
        db_session.add_all(
            [
                PendingMembership(
                    tenant_id=first_tenant.id, email="fay@example.com", role=Role.MEMBER
                ),
                PendingMembership(
                    tenant_id=second_tenant.id, email="fay@example.com", role=Role.VIEWER
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
        assert {(m.tenant_id, m.role) for m in memberships} == {
            (first_tenant.id, Role.MEMBER),
            (second_tenant.id, Role.VIEWER),
        }

        statuses = (
            await db_session.scalars(
                select(PendingMembership.status)
                .where(PendingMembership.email == "fay@example.com")
                .execution_options(populate_existing=True)
            )
        ).all()
        assert list(statuses) == [PendingMembershipStatus.ACCEPTED] * 2

    async def test_a_differently_cased_sign_in_email_still_matches_the_pending_row(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(
            PendingMembership(
                tenant_id=tenant.id, email="gus@example.com", role=Role.MEMBER
            )
        )
        await db_session.commit()
        cache = _override_verify_with_db(db_session)
        _seed_token(cache, email="gus@example.com", token="a-real-token")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/auth/magic-link/verify",
                params={"token": "a-real-token", "email": "Gus@Example.COM"},
            )

        assert response.status_code == 200
        user = await db_session.scalar(
            select(User).where(User.email == "gus@example.com")
        )
        assert user is not None
        membership = await db_session.scalar(
            select(TenantMembership).where(TenantMembership.user_id == user.id)
        )
        assert membership is not None
        assert membership.tenant_id == tenant.id

    async def test_a_pending_membership_past_its_ttl_is_not_activated(
        self, db_session: AsyncSession
    ) -> None:
        tenant = await _make_tenant(db_session)
        db_session.add(
            PendingMembership(
                tenant_id=tenant.id,
                email="hana@example.com",
                role=Role.MEMBER,
                created_at=datetime.now(UTC) - timedelta(days=8),
            )
        )
        await db_session.commit()
        cache = _override_verify_with_db(db_session)
        _seed_token(cache, email="hana@example.com", token="a-real-token")

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/api/v1/auth/magic-link/verify",
                params={"token": "a-real-token", "email": "hana@example.com"},
            )

        assert response.status_code == 200
        user = await db_session.scalar(
            select(User).where(User.email == "hana@example.com")
        )
        assert user is not None
        assert (
            await db_session.scalar(
                select(TenantMembership).where(TenantMembership.user_id == user.id)
            )
            is None
        )
