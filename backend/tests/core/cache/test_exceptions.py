from core.cache.exceptions import CacheError, CacheUnavailableError


def test_cache_unavailable_error_is_a_cache_error() -> None:
    assert issubclass(CacheUnavailableError, CacheError)


def test_cache_unavailable_error_carries_message() -> None:
    error = CacheUnavailableError("Redis GET failed for key 'x': connection refused")

    assert "connection refused" in str(error)
