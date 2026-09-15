"""Factory for instantiating a `CacheProvider` from configuration."""

from core.cache.config import CacheSettings
from core.cache.provider import CacheProvider
from core.cache.redis_provider import RedisCacheProvider


class CacheProviderFactory:
    """Builds the configured `CacheProvider`."""

    @staticmethod
    def create(settings: CacheSettings) -> CacheProvider:
        return RedisCacheProvider(redis_url=settings.redis_url)
