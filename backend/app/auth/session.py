"""Session issuance/validation (ADR-0006): a session is an opaque random id
whose SHA-256 hash keys a `CacheProvider` entry mapping to the signed-in
user's id, with a 30-day sliding TTL — refreshed on every successful lookup
so continued use keeps a session alive. The raw id is never stored; only
its hash is, so a leaked cache dump can't be replayed as a live cookie."""

import hashlib
import secrets
import uuid

from auth.config import SESSION_TTL_SECONDS
from core.cache.provider import CacheProvider

_SESSION_ID_BYTES = 32


def _hash_session_id(raw_session_id: str) -> str:
    return hashlib.sha256(raw_session_id.encode()).hexdigest()


def _session_key(session_hash: str) -> str:
    return f"session:{session_hash}"


class SessionService:
    def __init__(self, cache: CacheProvider) -> None:
        self._cache = cache

    async def create_session(self, user_id: uuid.UUID) -> str:
        """Issue a new opaque session id for `user_id`. Returns the raw id —
        the only place it exists outside the browser's cookie; the cache
        only ever holds its hash."""
        raw_session_id = secrets.token_urlsafe(_SESSION_ID_BYTES)
        await self._cache.set(
            _session_key(_hash_session_id(raw_session_id)),
            str(user_id),
            ttl_seconds=SESSION_TTL_SECONDS,
        )
        return raw_session_id

    async def resolve_user_id(self, raw_session_id: str) -> uuid.UUID | None:
        """Return the session's user id, sliding its TTL forward, or `None`
        if the session is missing or expired."""
        key = _session_key(_hash_session_id(raw_session_id))
        stored = await self._cache.get(key)
        if stored is None:
            return None
        await self._cache.expire(key, SESSION_TTL_SECONDS)
        return uuid.UUID(stored)

    async def delete_session(self, raw_session_id: str) -> None:
        """End a session. A no-op if it's already gone (expired, or
        already logged out) — logout must stay idempotent."""
        key = _session_key(_hash_session_id(raw_session_id))
        stored = await self._cache.get(key)
        if stored is None:
            return
        # Value-guarded delete rather than an unconditional one: if the
        # session was rotated (a fresh login) between the read above and
        # here, this leaves the new one alone instead of deleting it.
        await self._cache.delete_if_matches(key, stored)
