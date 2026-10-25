"""Unit tests for `MagicLinkService`/`MagicLinkVerificationService` (ADR-0006)."""

import hashlib
import uuid
from html import unescape

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


async def test_sends_plain_text_and_html_bodies_with_the_same_link_and_expiry() -> None:
    mailer = FakeMailer()
    service = _service(FakeCacheProvider(), mailer)

    await service.request_magic_link("jane@example.com")

    message = mailer.sent[0]
    plain, html = message["body"], message["html"]
    assert html is not None
    link = next(word for word in plain.split() if word.startswith(_VERIFY_URL))
    # The plain text keeps the link as a bare URL; the HTML escapes its `&`.
    assert link in unescape(html)
    ttl_minutes = MAGIC_LINK_TOKEN_TTL_SECONDS // 60
    assert f"{ttl_minutes} minutes" in plain
    assert f"Expires in {ttl_minutes} minutes and works once" in html


async def test_html_email_uses_no_images_or_external_fonts() -> None:
    mailer = FakeMailer()
    service = _service(FakeCacheProvider(), mailer)

    await service.request_magic_link("jane@example.com")

    html = mailer.sent[0]["html"]
    assert html is not None
    assert "<img" not in html
    assert "@import" not in html
    assert "<link" not in html
    assert "Sign in to Kith" in html
    assert "ignore this email" in html


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

    async def get_or_create_user(self, email: str) -> tuple[User, bool]:
        self.emails_seen.append(email)
        return User(id=uuid.uuid4(), email=email, email_verified=False, is_active=True), True


class FakeTenantsService:
    """Stands in for `TenantsService.activate_pending_memberships` — records
    calls so tests can assert *when* activation is attempted without a real
    TenantsRepository/Postgres; the conversion behavior itself is exercised
    in tests/tenants/test_repository.py."""

    def __init__(self) -> None:
        self.activation_calls: list[dict] = []

    async def activate_pending_memberships(self, *, user_id: uuid.UUID, email: str) -> None:
        self.activation_calls.append({"user_id": user_id, "email": email})


def _verification_service(
    cache: FakeCacheProvider,
) -> tuple[MagicLinkVerificationService, FakeUserRepository, FakeTenantsService]:
    user_repository = FakeUserRepository()
    tenants_service = FakeTenantsService()
    service = MagicLinkVerificationService(
        cache=cache,
        user_repository=user_repository,
        session_service=SessionService(cache),
        tenants_service=tenants_service,
    )
    return service, user_repository, tenants_service


def _seed_valid_token(cache: FakeCacheProvider, *, email: str, token: str) -> None:
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    cache._store[f"magic_link:token:{email.lower()}"] = token_hash


class TestVerify:
    async def test_valid_token_creates_a_user_and_issues_a_session(self) -> None:
        cache = FakeCacheProvider()
        service, user_repository, _ = _verification_service(cache)
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
        service, _, _ = _verification_service(cache)
        _seed_valid_token(cache, email="jane@example.com", token="a-real-token")

        await service.verify(email="jane@example.com", token="a-real-token")

        with pytest.raises(MagicLinkTokenInvalidError):
            await service.verify(email="jane@example.com", token="a-real-token")

    async def test_raises_when_no_token_was_ever_requested(self) -> None:
        cache = FakeCacheProvider()
        service, user_repository, _ = _verification_service(cache)

        with pytest.raises(MagicLinkTokenInvalidError):
            await service.verify(email="jane@example.com", token="whatever")

        assert user_repository.emails_seen == []

    async def test_raises_when_the_token_does_not_match_the_stored_hash(self) -> None:
        cache = FakeCacheProvider()
        service, _, _ = _verification_service(cache)
        _seed_valid_token(cache, email="jane@example.com", token="a-real-token")

        with pytest.raises(MagicLinkTokenInvalidError):
            await service.verify(email="jane@example.com", token="a-different-token")

    async def test_email_lookup_is_case_insensitive(self) -> None:
        cache = FakeCacheProvider()
        service, user_repository, _ = _verification_service(cache)
        _seed_valid_token(cache, email="jane@example.com", token="a-real-token")

        await service.verify(email="Jane@Example.com", token="a-real-token")

        assert user_repository.emails_seen == ["jane@example.com"]

    async def test_activates_a_pending_membership_for_the_signing_in_email(
        self,
    ) -> None:
        cache = FakeCacheProvider()
        service, _, tenants_service = _verification_service(cache)
        _seed_valid_token(cache, email="jane@example.com", token="a-real-token")

        user, _ = await service.verify(
            email="jane@example.com", token="a-real-token"
        )

        assert tenants_service.activation_calls == [
            {"user_id": user.id, "email": "jane@example.com"}
        ]

    async def test_does_not_activate_anything_for_an_invalid_token(self) -> None:
        cache = FakeCacheProvider()
        service, _, tenants_service = _verification_service(cache)

        with pytest.raises(MagicLinkTokenInvalidError):
            await service.verify(email="jane@example.com", token="whatever")

        assert tenants_service.activation_calls == []

    async def test_email_is_trimmed_and_lowercased_before_it_is_written_or_matched(
        self,
    ) -> None:
        """One canonical form, so the users row and any Pending Membership
        (stored normalized, see ck_pending_memberships_email_normalized)
        meet on the same string."""
        cache = FakeCacheProvider()
        service, user_repository, tenants_service = _verification_service(cache)
        _seed_valid_token(cache, email="jane@example.com", token="a-real-token")

        user, _ = await service.verify(
            email="  Jane@Example.COM ", token="a-real-token"
        )

        assert user_repository.emails_seen == ["jane@example.com"]
        assert tenants_service.activation_calls == [
            {"user_id": user.id, "email": "jane@example.com"}
        ]
