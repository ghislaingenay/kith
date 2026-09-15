"""Unit tests for `RedisCacheProvider` against a mocked `redis.asyncio.Redis`
client. No real Redis needed here — mirrors this project's convention of
testing repository/adapter logic against a mocked client rather than live
infrastructure (see tests/upload/test_repository.py).
"""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import RedisError

from core.cache.exceptions import CacheUnavailableError
from core.cache.redis_provider import RedisCacheProvider

_KEY = "dedup:hash:abc123"
_VALUE = "originals/2026/08/14/file.jpg"
_TTL = 86400


@pytest.fixture()
def mock_client() -> AsyncMock:
    return AsyncMock()


@pytest.fixture()
def provider(mock_client: AsyncMock) -> RedisCacheProvider:
    cache_provider = RedisCacheProvider(redis_url="redis://localhost:6379/0")
    cache_provider._client = mock_client
    return cache_provider


async def test_get_returns_value(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.get.return_value = _VALUE

    result = await provider.get(_KEY)

    assert result == _VALUE
    mock_client.get.assert_awaited_once_with(_KEY)


async def test_get_returns_none_when_absent(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.get.return_value = None

    assert await provider.get(_KEY) is None


async def test_get_raises_cache_unavailable_on_redis_error(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.get.side_effect = RedisError("connection refused")

    with pytest.raises(CacheUnavailableError):
        await provider.get(_KEY)


async def test_set_passes_ttl_through(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    await provider.set(_KEY, _VALUE, _TTL)

    mock_client.set.assert_awaited_once_with(_KEY, _VALUE, ex=_TTL)


async def test_set_raises_cache_unavailable_on_redis_error(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.set.side_effect = RedisError("connection refused")

    with pytest.raises(CacheUnavailableError):
        await provider.set(_KEY, _VALUE, _TTL)


async def test_set_if_not_exists_returns_true_when_acquired(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.set.return_value = True

    acquired = await provider.set_if_not_exists(_KEY, _VALUE, _TTL)

    assert acquired is True
    mock_client.set.assert_awaited_once_with(_KEY, _VALUE, nx=True, ex=_TTL)


async def test_set_if_not_exists_returns_false_when_already_held(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.set.return_value = None

    acquired = await provider.set_if_not_exists(_KEY, _VALUE, _TTL)

    assert acquired is False


async def test_set_if_not_exists_raises_cache_unavailable_on_redis_error(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.set.side_effect = RedisError("connection refused")

    with pytest.raises(CacheUnavailableError):
        await provider.set_if_not_exists(_KEY, _VALUE, _TTL)


async def test_expire_passes_ttl_through(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    await provider.expire(_KEY, _TTL)

    mock_client.expire.assert_awaited_once_with(_KEY, _TTL)


async def test_expire_raises_cache_unavailable_on_redis_error(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.expire.side_effect = RedisError("connection refused")

    with pytest.raises(CacheUnavailableError):
        await provider.expire(_KEY, _TTL)


async def test_delete_if_matches_returns_true_when_deleted(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.eval.return_value = 1

    deleted = await provider.delete_if_matches(_KEY, "token-abc")

    assert deleted is True
    mock_client.eval.assert_awaited_once()


async def test_delete_if_matches_returns_false_when_value_mismatched(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.eval.return_value = 0

    deleted = await provider.delete_if_matches(_KEY, "token-abc")

    assert deleted is False


async def test_delete_if_matches_raises_cache_unavailable_on_redis_error(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    mock_client.eval.side_effect = RedisError("connection refused")

    with pytest.raises(CacheUnavailableError):
        await provider.delete_if_matches(_KEY, "token-abc")


async def test_close_closes_the_underlying_client(
    provider: RedisCacheProvider, mock_client: AsyncMock
) -> None:
    await provider.close()

    mock_client.aclose.assert_awaited_once()
