"""Unit tests for `MagicLinkService` (ADR-0006)."""

import hashlib

import pytest

from auth.config import (
    MAGIC_LINK_RATE_LIMIT_PER_HOUR,
    MAGIC_LINK_TOKEN_TTL_SECONDS,
)
from auth.service import MagicLinkService
from core.ratelimit.counter_limiter import CounterLimiter
from core.ratelimit.exceptions import RateLimitExceededError
from tests.support.fake_cache import FakeCacheProvider
from tests.support.fake_mailer import FakeMailer

_VERIFY_URL = "http://localhost:8000/api/v1/auth/magic-link/verify"


def _service(cache: FakeCacheProvider, mailer: FakeMailer) -> MagicLinkService:
    return MagicLinkService(
        cache=cache,
        mailer=mailer,
        limiter=CounterLimiter(cache),
        verify_url=_VERIFY_URL,
    )


async def test_stores_hashed_token_in_cache_keyed_to_email() -> None:
    cache = FakeCacheProvider()
    service = _service(cache, FakeMailer())

    await service.request_magic_link("jane@example.com")

    stored_hash = await cache.get("magic_link:token:jane@example.com")
    assert stored_hash is not None
    # The raw token is never stored — only its SHA-256 hex digest.
    assert len(stored_hash) == 64
    assert all(c in "0123456789abcdef" for c in stored_hash)


async def test_sends_email_containing_a_verify_link_with_the_token() -> None:
    cache = FakeCacheProvider()
    mailer = FakeMailer()
    service = _service(cache, mailer)

    await service.request_magic_link("jane@example.com")

    assert len(mailer.sent) == 1
    message = mailer.sent[0]
    assert message["to"] == "jane@example.com"
    assert _VERIFY_URL in message["body"]
    assert "token=" in message["body"]

    # The token in the email hashes to what's stored in the cache.
    token = message["body"].split("token=")[1].split("&")[0]
    stored_hash = await cache.get("magic_link:token:jane@example.com")
    assert hashlib.sha256(token.encode()).hexdigest() == stored_hash


async def test_normalizes_email_case_for_the_cache_key() -> None:
    cache = FakeCacheProvider()
    service = _service(cache, FakeMailer())

    await service.request_magic_link("Jane@Example.com")

    assert await cache.get("magic_link:token:jane@example.com") is not None


async def test_allows_up_to_the_per_hour_limit() -> None:
    cache = FakeCacheProvider()
    service = _service(cache, FakeMailer())

    for _ in range(MAGIC_LINK_RATE_LIMIT_PER_HOUR):
        await service.request_magic_link("jane@example.com")


async def test_raises_rate_limit_exceeded_past_the_per_hour_limit() -> None:
    cache = FakeCacheProvider()
    mailer = FakeMailer()
    service = _service(cache, mailer)

    for _ in range(MAGIC_LINK_RATE_LIMIT_PER_HOUR):
        await service.request_magic_link("jane@example.com")

    with pytest.raises(RateLimitExceededError):
        await service.request_magic_link("jane@example.com")

    # The 6th call never sent an email or minted a new token.
    assert len(mailer.sent) == MAGIC_LINK_RATE_LIMIT_PER_HOUR


async def test_rate_limit_is_scoped_per_email() -> None:
    cache = FakeCacheProvider()
    mailer = FakeMailer()
    service = _service(cache, mailer)

    for _ in range(MAGIC_LINK_RATE_LIMIT_PER_HOUR):
        await service.request_magic_link("jane@example.com")

    # A different email hasn't touched its own budget yet.
    await service.request_magic_link("john@example.com")

    assert len(mailer.sent) == MAGIC_LINK_RATE_LIMIT_PER_HOUR + 1


async def test_token_ttl_matches_the_documented_15_minutes() -> None:
    assert MAGIC_LINK_TOKEN_TTL_SECONDS == 15 * 60
