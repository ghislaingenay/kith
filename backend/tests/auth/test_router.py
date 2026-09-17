"""HTTP-level tests for POST /auth/magic-link — dependency overrides only,
no DB (mirrors tests/tenants/test_router.py's ASGITransport pattern). Uses
the real `MagicLinkService` wired to `FakeCacheProvider`/`FakeMailer` so the
enumeration-safety and rate-limit behavior are exercised end to end, not
mocked away."""

import pytest
from httpx import ASGITransport, AsyncClient

from auth.config import MAGIC_LINK_RATE_LIMIT_PER_HOUR
from auth.dependencies import get_magic_link_service
from auth.service import MagicLinkService
from core.ratelimit.counter_limiter import CounterLimiter
from main import app
from tests.support.fake_cache import FakeCacheProvider
from tests.support.fake_mailer import FakeMailer

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
