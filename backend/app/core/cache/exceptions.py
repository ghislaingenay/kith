"""Provider-agnostic exceptions for the cache abstraction."""


class CacheError(Exception):
    """Base exception for all cache provider failures."""


class CacheUnavailableError(CacheError):
    """Raised when the cache backend cannot be reached (connection failure, timeout)."""
