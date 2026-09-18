"""Unit tests for `MagicLinkService`/`MagicLinkVerificationService` (ADR-0006)."""

import hashlib
import uuid

import pytest

from auth.config import (
    MAGIC_LINK_RATE_LIMIT_PER_HOUR,
    MAGIC_LINK_TOKEN_TTL_SECONDS,
)
from auth.exceptions import MagicLinkTokenInvalidError
from auth.service import MagicLinkService, MagicLinkVerificationService
from auth.session import SessionService
from core.ratelimit.counter_limiter import CounterLimiter
from core.ratelimit.exceptions import RateLimitExceededError
from tests.support.fake_cache import FakeCacheProvider
from tests.support.fake_mailer import FakeMailer
from users.models import User

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


class FakeUserRepository:
    """Stands in for `UserRepository.get_or_create_user` — always
    "creates" a fresh User, since verifying which existing/new case
    applies is `UserRepository`'s own, already-tested job."""

    def __init__(self) -> None:
        self.emails_seen: list[str] = []

    async def get_or_create_user(self, email: str) -> User:
        self.emails_seen.append(email)
        return User(id=uuid.uuid4(), email=email, email_verified=False, is_active=True)


def _verification_service(
    cache: FakeCacheProvider,
) -> tuple[MagicLinkVerificationService, FakeUserRepository]:
    user_repository = FakeUserRepository()
    service = MagicLinkVerificationService(
        cache=cache,
        user_repository=user_repository,
        session_service=SessionService(cache),
    )
    return service, user_repository


def _seed_valid_token(cache: FakeCacheProvider, *, email: str, token: str) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cache._store[f"magic_link:token:{email.lower()}"] = token_hash


class TestVerify:
    async def test_valid_token_creates_a_user_and_issues_a_session(self) -> None:
        cache = FakeCacheProvider()
        service, user_repository = _verification_service(cache)
        _seed_valid_token(cache, email="jane@example.com", token="a-real-token")

        user, raw_session_id = await service.verify(
            email="jane@example.com", token="a-real-token"
        )

        assert user_repository.emails_seen == ["jane@example.com"]
        assert raw_session_id
        session_service = SessionService(cache)
        assert await session_service.resolve_user_id(raw_session_id) == user.id

    async def test_valid_token_is_consumed_and_cannot_be_reused(self) -> None:
        cache = FakeCacheProvider()
        service, _ = _verification_service(cache)
        _seed_valid_token(cache, email="jane@example.com", token="a-real-token")

        await service.verify(email="jane@example.com", token="a-real-token")

        with pytest.raises(MagicLinkTokenInvalidError):
            await service.verify(email="jane@example.com", token="a-real-token")

    async def test_raises_when_no_token_was_ever_requested(self) -> None:
        cache = FakeCacheProvider()
        service, user_repository = _verification_service(cache)

        with pytest.raises(MagicLinkTokenInvalidError):
            await service.verify(email="jane@example.com", token="whatever")

        assert user_repository.emails_seen == []

    async def test_raises_when_the_token_does_not_match_the_stored_hash(self) -> None:
        cache = FakeCacheProvider()
        service, _ = _verification_service(cache)
        _seed_valid_token(cache, email="jane@example.com", token="a-real-token")

        with pytest.raises(MagicLinkTokenInvalidError):
            await service.verify(email="jane@example.com", token="a-different-token")

    async def test_email_lookup_is_case_insensitive(self) -> None:
        cache = FakeCacheProvider()
        service, user_repository = _verification_service(cache)
        _seed_valid_token(cache, email="jane@example.com", token="a-real-token")

        await service.verify(email="Jane@Example.com", token="a-real-token")

        assert user_repository.emails_seen == ["Jane@Example.com"]
