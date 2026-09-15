"""Factory for instantiating the rate limiter from configuration."""

from redis import asyncio as redis_asyncio

from core.cache.config import CacheSettings
from core.ratelimit.limiter import MultiWindowLimiter, SlidingWindowLimiter


class RateLimiterFactory:
    """Builds the configured rate limiter.

    Reuses `CacheSettings.redis_url` rather than introducing a second env
    var — the limiter needs a raw `redis.asyncio.Redis` client to run its
    Lua script (`CacheProvider` doesn't expose `eval`), so it opens its own
    connection pool against the same Redis instance `cache_provider` uses.
    """

    @staticmethod
    def create(settings: CacheSettings) -> MultiWindowLimiter:
        client = redis_asyncio.from_url(settings.redis_url, decode_responses=True)
        return SlidingWindowLimiter(client)
