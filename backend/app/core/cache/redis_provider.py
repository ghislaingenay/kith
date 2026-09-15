"""Redis-backed cache provider."""

from typing import Protocol, cast

from redis import asyncio as redis_asyncio
from redis.exceptions import RedisError

from core.cache.exceptions import CacheUnavailableError
from core.cache.provider import CacheProvider

# KEYS[1] = lock/value key, ARGV[1] = expected current value. Atomic
# read-compare-delete via Lua so a lock's TTL expiring mid-release can never
_DELETE_IF_MATCHES_SCRIPT = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""


class _RedisClientProtocol(Protocol):
    """The subset of `redis.asyncio.Redis` this provider calls.

    redis-py ships inline types, but which specific methods are actually
    annotated varies by installed version (e.g. `eval` lacks coverage in some
    versions, other methods in others) — casting `from_url()`'s result to
    this locally-owned Protocol means every call below is checked against a
    signature we control, not whatever a given redis-py version happens to
    provide, so this file's type-checking is deterministic regardless of
    which version is installed.
    """

    async def get(self, key: str) -> str | None:
        ...

    async def set(
        self, key: str, value: str, *, ex: int | None = None, nx: bool = False
    ) -> object:
        ...

    async def expire(self, key: str, seconds: int) -> object:
        ...

    async def eval(self, script: str, numkeys: int, *keys_and_args: str) -> object:
        ...

    async def aclose(self) -> None:
        ...


class RedisCacheProvider(CacheProvider):
    """`CacheProvider` backed by `redis.asyncio.Redis`."""

    def __init__(self, redis_url: str) -> None:
        self._client = cast(
            _RedisClientProtocol,
            redis_asyncio.from_url(redis_url, decode_responses=True),
        )

    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)
        except RedisError as exc:
            raise CacheUnavailableError(
                f"Redis GET failed for key {key!r}: {exc}"
            ) from exc

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        try:
            await self._client.set(key, value, ex=ttl_seconds)
        except RedisError as exc:
            raise CacheUnavailableError(
                f"Redis SET failed for key {key!r}: {exc}"
            ) from exc

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int) -> bool:
        try:
            result = await self._client.set(key, value, nx=True, ex=ttl_seconds)
        except RedisError as exc:
            raise CacheUnavailableError(
                f"Redis SET NX failed for key {key!r}: {exc}"
            ) from exc
        return bool(result)

    async def expire(self, key: str, ttl_seconds: int) -> None:
        try:
            await self._client.expire(key, ttl_seconds)
        except RedisError as exc:
            raise CacheUnavailableError(
                f"Redis EXPIRE failed for key {key!r}: {exc}"
            ) from exc

    async def delete_if_matches(self, key: str, expected_value: str) -> bool:
        try:
            result = await self._client.eval(
                _DELETE_IF_MATCHES_SCRIPT, 1, key, expected_value
            )
        except RedisError as exc:
            raise CacheUnavailableError(
                f"Redis DEL failed for key {key!r}: {exc}"
            ) from exc
        return bool(result)

    async def close(self) -> None:
        await self._client.aclose()
