"""Unit tests for `CounterLimiter` — the simple, `CacheProvider`-backed
rate limiter used by the magic-link flow."""

import pytest
from core.ratelimit.counter_limiter import CounterLimiter
from core.ratelimit.exceptions import RateLimitExceededError

from tests.support.fake_cache import FakeCacheProvider


async def test_allows_calls_under_the_limit() -> None:
    limiter = CounterLimiter(FakeCacheProvider())

    for _ in range(3):
        await limiter.check_and_increment("k", limit=3, window_seconds=3600)


async def test_raises_once_the_limit_is_reached() -> None:
    limiter = CounterLimiter(FakeCacheProvider())

    for _ in range(3):
        await limiter.check_and_increment("k", limit=3, window_seconds=3600)

    with pytest.raises(RateLimitExceededError):
        await limiter.check_and_increment("k", limit=3, window_seconds=3600)


async def test_exception_carries_limit_and_retry_after() -> None:
    cache = FakeCacheProvider()
    limiter = CounterLimiter(cache)
    for _ in range(2):
        await limiter.check_and_increment("k", limit=2, window_seconds=1800)

    with pytest.raises(RateLimitExceededError) as exc_info:
        await limiter.check_and_increment("k", limit=2, window_seconds=1800)

    assert exc_info.value.limit == 2
    assert exc_info.value.remaining == 0
    assert exc_info.value.retry_after.total_seconds() == 1800


async def test_different_keys_have_independent_budgets() -> None:
    limiter = CounterLimiter(FakeCacheProvider())

    for _ in range(2):
        await limiter.check_and_increment("a", limit=2, window_seconds=3600)

    # "b" hasn't made any calls yet, so it isn't affected by "a" being at budget.
    await limiter.check_and_increment("b", limit=2, window_seconds=3600)


async def test_stores_the_count_under_a_namespaced_key_not_the_raw_key() -> None:
    cache = FakeCacheProvider()
    limiter = CounterLimiter(cache)

    await limiter.check_and_increment("some-key", limit=5, window_seconds=3600)

    assert await cache.get("some-key") is None
    assert await cache.get("ratelimit:counter:some-key") == "1"
