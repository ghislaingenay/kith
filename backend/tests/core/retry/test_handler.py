import pytest

from core.retry.config import RetrySettings
from core.retry.exceptions import RetryExhaustedError
from core.retry.handler import RetryHandler

_FAST_SETTINGS = RetrySettings(
    max_attempts=3, base_delay=0.001, max_delay=0.01, jitter=False
)


class _FlakyServiceError(Exception):
    pass


async def test_succeeds_on_first_attempt_without_retrying() -> None:
    handler = RetryHandler(_FAST_SETTINGS)
    calls = 0

    async def func() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = await handler.execute(func)

    assert result == "ok"
    assert calls == 1


async def test_retries_then_succeeds() -> None:
    handler = RetryHandler(_FAST_SETTINGS)
    calls = 0

    async def func() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _FlakyServiceError("temporary failure")
        return "ok"

    result = await handler.execute(func, retry_on=(_FlakyServiceError,))

    assert result == "ok"
    assert calls == 3


async def test_raises_retry_exhausted_error_after_max_attempts() -> None:
    handler = RetryHandler(_FAST_SETTINGS)
    calls = 0

    async def func() -> str:
        nonlocal calls
        calls += 1
        raise _FlakyServiceError("always fails")

    with pytest.raises(RetryExhaustedError) as exc_info:
        await handler.execute(func, retry_on=(_FlakyServiceError,))

    assert calls == _FAST_SETTINGS.max_attempts
    assert exc_info.value.attempts == _FAST_SETTINGS.max_attempts
    assert isinstance(exc_info.value.last_exception, _FlakyServiceError)


async def test_does_not_retry_on_non_matching_exception() -> None:
    handler = RetryHandler(_FAST_SETTINGS)
    calls = 0

    async def func() -> str:
        nonlocal calls
        calls += 1
        raise ValueError("not retryable")

    with pytest.raises(ValueError):
        await handler.execute(func, retry_on=(_FlakyServiceError,))

    assert calls == 1


async def test_per_call_override_takes_precedence_over_settings() -> None:
    handler = RetryHandler(_FAST_SETTINGS)
    calls = 0

    async def func() -> str:
        nonlocal calls
        calls += 1
        raise _FlakyServiceError("always fails")

    with pytest.raises(RetryExhaustedError) as exc_info:
        await handler.execute(func, retry_on=(_FlakyServiceError,), max_attempts=1)

    assert calls == 1
    assert exc_info.value.attempts == 1
