"""Minimal auth service surface used by dependencies and tests."""

import hashlib
import secrets
from types import SimpleNamespace
from urllib.parse import quote

from auth.config import (
    MAGIC_LINK_RATE_LIMIT_PER_HOUR,
    MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS,
    MAGIC_LINK_TOKEN_TTL_SECONDS,
)
from core.cache.provider import CacheProvider
from core.mail.provider import Mailer
from core.ratelimit.counter_limiter import CounterLimiter


async def authenticate_request(*_, **__) -> SimpleNamespace:
    return SimpleNamespace(is_signed_in=False, payload=None, reason="unauthenticated")


def _token_key(email: str) -> str:
    return f"magic_link:token:{email.lower()}"


def _rate_limit_key(email: str) -> str:
    return f"magic_link:{email.lower()}"


class MagicLinkService:
    """Requests a magic-link sign-in email (ADR-0006). Deliberately never
    checks whether `email` has an account — every syntactically valid work
    email gets the same token-generation-and-send path and the same
    response, which is what makes the endpoint enumeration-safe by
    construction rather than by a special-cased branch."""

    def __init__(
        self,
        cache: CacheProvider,
        mailer: Mailer,
        limiter: CounterLimiter,
        verify_url: str,
    ) -> None:
        self._cache = cache
        self._mailer = mailer
        self._limiter = limiter
        self._verify_url = verify_url

    async def request_magic_link(self, email: str) -> None:
        await self._limiter.check_and_increment(
            key=_rate_limit_key(email),
            limit=MAGIC_LINK_RATE_LIMIT_PER_HOUR,
            window_seconds=MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS,
        )

        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        await self._cache.set(
            _token_key(email), token_hash, ttl_seconds=MAGIC_LINK_TOKEN_TTL_SECONDS
        )

        link = f"{self._verify_url}?token={token}&email={quote(email)}"
        ttl_minutes = MAGIC_LINK_TOKEN_TTL_SECONDS // 60
        await self._mailer.send(
            to=email,
            subject="Your Kith sign-in link",
            body=(
                f"Use the link below to sign in. It expires in {ttl_minutes} minutes "
                f"and can only be used once.\n\n{link}"
            ),
        )
