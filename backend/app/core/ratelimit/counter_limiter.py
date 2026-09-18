"""Simple single-window rate limiter for callers that don't need
`limiter.py`'s dual-window, Redis-eval sliding window — just "N per
arbitrary string key per window," backed by `CacheProvider` so it's testable
with `FakeCacheProvider` instead of a real Redis client."""

from datetime import timedelta

from core.cache.provider import CacheProvider
from core.ratelimit.exceptions import RateLimitExceededError

_KEY_PREFIX = "ratelimit:counter:"


class CounterLimiter:
    """Enforces a fixed budget per arbitrary string key over a rolling
    window, backed by `CacheProvider.get`/`set`.

    Not atomic: `CacheProvider` exposes no increment primitive, so a
    read-then-write race lets two concurrent calls for the same key both
    read the same count before either writes it back — acceptable for
    generous, non-security-boundary budgets (e.g. an email-send rate limit)
    but not a fit for anything that must be exact under contention (that's
    what `limiter.py`'s Lua-atomic `SlidingWindowLimiter` is for). Each call
    also refreshes the key's TTL, so a steady trickle of calls keeps the
    window alive rather than expiring mid-use — a rolling, not fixed,
    window in practice.
    """

    def __init__(self, cache: CacheProvider) -> None:
        self._cache = cache

    async def check_and_increment(
        self, key: str, limit: int, window_seconds: int
    ) -> None:
        """Raise `RateLimitExceededError` if `key` has already reached
        `limit` calls within the current window; otherwise record this call
        and let it through."""
        cache_key = f"{_KEY_PREFIX}{key}"
        raw = await self._cache.get(cache_key)
        count = int(raw) if raw is not None else 0
        if count >= limit:
            raise RateLimitExceededError(
                limit=limit,
                remaining=0,
                retry_after=timedelta(seconds=window_seconds),
            )
        await self._cache.set(cache_key, str(count + 1), ttl_seconds=window_seconds)
