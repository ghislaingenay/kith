from core.cache.config import CacheSettings
from core.cache.factory import CacheProviderFactory
from core.cache.redis_provider import RedisCacheProvider

_REDIS_URL = "redis://localhost:6379/0"


def test_create_returns_redis_cache_provider() -> None:
    provider = CacheProviderFactory.create(CacheSettings(redis_url=_REDIS_URL))

    assert isinstance(provider, RedisCacheProvider)
