"""Abstract interface all cache backends implement."""

from abc import ABC, abstractmethod


class CacheProvider(ABC):
    """Common key-value cache operations every backend (Redis, Memcached) must support.

    Implementations must raise only `CacheUnavailableError` (from
    `src/core/cache/exceptions.py`) on connectivity failures — never leak
    provider-specific client exceptions across this boundary, so callers can
    catch one exception type to trigger graceful degradation.
    """

    @abstractmethod
    async def get(self, key: str) -> str | None:
        """Return the value for `key`, or `None` if absent."""

    @abstractmethod
    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        """Set `key` to `value`, expiring after `ttl_seconds`."""

    @abstractmethod
    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Atomically set `key` to `value` only if it doesn't already exist.

        Returns `True` if this call set the key, `False` if it already existed.
        """

    @abstractmethod
    async def expire(self, key: str, ttl_seconds: int) -> None:
        """Reset `key`'s TTL to `ttl_seconds` without changing its value."""

    @abstractmethod
    async def delete_if_matches(self, key: str, expected_value: str) -> bool:
        """Atomically delete `key` only if its current value equals `expected_value`.

        Used to release a value-guarded lock without deleting one a different
        holder has since acquired (e.g. after this holder's TTL expired).
        Returns `True` if deleted, `False` if the key was absent or held a
        different value.
        """

    @abstractmethod
    async def close(self) -> None:
        """Release any held connections. Called once during app shutdown."""
