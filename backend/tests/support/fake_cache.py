"""An in-memory fake `CacheProvider` for tests that need real get/set
round-trip behavior (e.g. "does what we write come back out the same way")
without a real Redis. For tests that only need to assert *how* the cache
provider was called, prefer `unittest.mock.AsyncMock(spec=CacheProvider)`
instead — this fake is for round-trip behavior tests.
"""

from core.cache.provider import CacheProvider


class FakeCacheProvider(CacheProvider):
    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self.closed = False

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        self._store[key] = value

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int) -> bool:
        if key in self._store:
            return False
        self._store[key] = value
        return True

    async def expire(self, key: str, ttl_seconds: int) -> None:
        return None

    async def delete_if_matches(self, key: str, expected_value: str) -> bool:
        if self._store.get(key) == expected_value:
            del self._store[key]
            return True
        return False

    async def close(self) -> None:
        self.closed = True
