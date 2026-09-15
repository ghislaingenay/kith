"""Sliding-window rate limiter backed by Redis."""

import math
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from redis import asyncio as redis_asyncio
from redis.exceptions import RedisError

from core.ratelimit.exceptions import RateLimitUnavailableError

KEY_PREFIX = "ratelimit:"

_MINUTE = timedelta(minutes=1)
_HOUR = timedelta(hours=1)

# Increments the current bucket (creating it with a TTL on first write) and
# returns it alongside the previous bucket's count, so the caller can apply
# the sliding-window weighting without a second round trip.
_INCR_FUNC = """
local function incr(curKey, prevKey, ttl)
    local current = redis.call('INCR', curKey)
    if current == 1 then
        redis.call('PEXPIRE', curKey, ttl)
    end
    local previous = redis.call('GET', prevKey)
    if previous == false then
        previous = '0'
    end
    return {current, previous}
end
"""

# Checks both minute and hour windows in one Redis round trip.
_BOTH_WINDOWS_SCRIPT = (
    _INCR_FUNC
    + """
local minute = incr(KEYS[1], KEYS[2], ARGV[1])
local hour = incr(KEYS[3], KEYS[4], ARGV[2])
return {minute[1], minute[2], hour[1], hour[2]}
"""
)


class Decision:
    """The outcome of a rate-limit check for one window."""

    def __init__(
        self,
        allowed: bool,
        limit: int,
        remaining: int,
        retry_after: timedelta | None,
    ) -> None:
        self.allowed = allowed
        self.limit = limit
        self.remaining = remaining
        self.retry_after = retry_after


class _RedisClientProtocol(Protocol):
    """The subset of redis.asyncio.Redis the limiter needs."""

    async def eval(
        self,
        script: str,
        numkeys: int,
        *keys_and_args: str | int,
    ) -> list[int | str]:
        ...

    async def aclose(self) -> None:
        ...


class MultiWindowLimiter(ABC):
    """Enforces per-tenant, per-user rate limits across minute and hour windows."""

    @abstractmethod
    async def allow_both(
        self,
        tenant_id: UUID,
        user_id: UUID,
        minute_limit: int,
        hour_limit: int,
    ) -> tuple[Decision, Decision]:
        """Check both minute and hour windows in a single call.

        Returns:
            (minute_decision, hour_decision)
        """

    @abstractmethod
    async def close(self) -> None:
        """Release any held connections. Called once during app shutdown."""


class SlidingWindowLimiter(MultiWindowLimiter):
    """Sliding-window rate limiter using Redis.

    Implements the Cloudflare-style two-bucket sliding-window approximation:
    the current fixed-size bucket count is combined with a weighted fraction
    of the previous bucket's count, based on how far into the current bucket
    the request falls.
    """

    def __init__(self, redis_client: redis_asyncio.Redis) -> None:
        self._redis: _RedisClientProtocol = redis_client  # type: ignore

    async def allow_both(
        self,
        tenant_id: UUID,
        user_id: UUID,
        minute_limit: int,
        hour_limit: int,
    ) -> tuple[Decision, Decision]:
        """Check minute and hour windows with a single Redis round trip."""
        key = f"{tenant_id}:{user_id}"

        now = datetime.now(timezone.utc)
        minute_bucket = _truncate(now, _MINUTE)
        hour_bucket = _truncate(now, _HOUR)

        keys = [
            _bucket_key(key, "minute", minute_bucket),
            _bucket_key(key, "minute", minute_bucket - _MINUTE),
            _bucket_key(key, "hour", hour_bucket),
            _bucket_key(key, "hour", hour_bucket - _HOUR),
        ]

        try:
            result = await self._redis.eval(
                _BOTH_WINDOWS_SCRIPT,
                4,
                *keys,
                int((2 * _MINUTE).total_seconds() * 1000),
                int((2 * _HOUR).total_seconds() * 1000),
            )
        except RedisError as exc:
            raise RateLimitUnavailableError(
                f"ratelimit: eval both windows: {exc}"
            ) from exc

        if not isinstance(result, list) or len(result) != 4:
            raise RateLimitUnavailableError(
                f"ratelimit: unexpected eval result shape: {result!r}"
            )

        minute_current, minute_previous = _to_counts(result[0], result[1])
        hour_current, hour_previous = _to_counts(result[2], result[3])

        minute_decision = _build_decision(
            minute_current, minute_previous, now, minute_bucket, _MINUTE, minute_limit
        )
        hour_decision = _build_decision(
            hour_current, hour_previous, now, hour_bucket, _HOUR, hour_limit
        )

        return minute_decision, hour_decision

    async def close(self) -> None:
        await self._redis.aclose()


def _bucket_key(key: str, window: str, bucket_start: datetime) -> str:
    """Generates a Redis key for a specific bucket."""
    return f"{KEY_PREFIX}{key}:{window}:{int(bucket_start.timestamp())}"


def _truncate(dt: datetime, duration: timedelta) -> datetime:
    """Truncates a datetime to the start of a bucket."""
    seconds = int(duration.total_seconds())
    timestamp = int(dt.timestamp())
    truncated_timestamp = (timestamp // seconds) * seconds
    return datetime.fromtimestamp(truncated_timestamp, tz=timezone.utc)


def _build_decision(
    current: int,
    previous: int,
    now: datetime,
    bucket_start: datetime,
    duration: timedelta,
    limit: int,
) -> Decision:
    """Builds a Decision using sliding-window approximation."""
    elapsed = now - bucket_start
    weight = max(1 - (elapsed.total_seconds() / duration.total_seconds()), 0)

    weighted_count = current + (previous * weight)

    remaining = max(limit - math.ceil(weighted_count), 0)

    return Decision(
        allowed=weighted_count <= limit,
        limit=limit,
        remaining=remaining,
        retry_after=max(duration - elapsed, timedelta(0)),
    )


def _to_counts(cur_raw: int | str, prev_raw: int | str) -> tuple[int, int]:
    """Converts Redis response values to integer counts."""
    return _to_int(cur_raw), _to_int(prev_raw)


def _to_int(value: int | str) -> int:
    """Converts a value to an integer."""
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise ValueError(f"Unexpected value type: {type(value)}")
