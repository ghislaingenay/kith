"""Magic-link issuance and verification (ADR-0006)."""

import hashlib
import secrets
from urllib.parse import quote

from auth.config import (
    MAGIC_LINK_RATE_LIMIT_PER_HOUR,
    MAGIC_LINK_RATE_LIMIT_WINDOW_SECONDS,
    MAGIC_LINK_TOKEN_TTL_SECONDS,
)
from auth.exceptions import MagicLinkTokenInvalidError
from auth.session import SessionService
from core.cache.provider import CacheProvider
from core.mail.provider import Mailer
from core.ratelimit.counter_limiter import CounterLimiter
from users.models import User
from users.repository import UserRepository


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


class MagicLinkVerificationService:
    """Orchestrates `GET /auth/magic-link/verify`: atomically consumes the
    single-use token, creates or fetches the User (first sign-in is
    signup — see `UserRepository.get_or_create_user`), and issues a
    session. Kept separate from `MagicLinkService` (which only issues the
    request-side token) so that class's tests don't need a
    `UserRepository`/`SessionService`."""

    def __init__(
        self,
        cache: CacheProvider,
        user_repository: UserRepository,
        session_service: SessionService,
    ) -> None:
        self._cache = cache
        self._user_repository = user_repository
        self._session_service = session_service

    async def verify(self, *, email: str, token: str) -> tuple[User, str]:
        """Returns the signed-in `User` and the raw session id to set as
        the session cookie. Raises `MagicLinkTokenInvalidError` if `token`
        is missing, expired, or already used."""
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        consumed = await self._cache.delete_if_matches(_token_key(email), token_hash)
        if not consumed:
            raise MagicLinkTokenInvalidError()

        user = await self._user_repository.get_or_create_user(email)
        raw_session_id = await self._session_service.create_session(user.id)
        return user, raw_session_id
