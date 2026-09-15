"""Retry handler with exponential backoff, configurable via `RetrySettings`."""

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from core.retry.config import RetrySettings
from core.retry.exceptions import RetryError, RetryExhaustedError

T = TypeVar("T")


class RetryHandler:
    """Retries an async callable with exponential backoff.

    Defaults come from `RetrySettings` (env-driven via `RETRY_MAX_ATTEMPTS`,
    `RETRY_BASE_DELAY`, `RETRY_MAX_DELAY`, `RETRY_JITTER`); any of them can be
    overridden per call through `execute(...)` without touching the
    environment.
    """

    def __init__(self, settings: RetrySettings) -> None:
        self._settings = settings

    async def execute(
        self,
        func: Callable[[], Awaitable[T]],
        *,
        # It's a tuple of exception types the handler should catch and retry on
        # e.g. retry_on=(ConnectionError, TimeoutError) retries only network-ish failures.
        retry_on: tuple[type[BaseException], ...] = (Exception,),
        max_attempts: int | None = None,
        base_delay: float | None = None,
        max_delay: float | None = None,
        jitter: bool | None = None,
    ) -> T:
        attempts = (
            max_attempts if max_attempts is not None else self._settings.max_attempts
        )
        delay = base_delay if base_delay is not None else self._settings.base_delay
        ceiling = max_delay if max_delay is not None else self._settings.max_delay
        use_jitter = jitter if jitter is not None else self._settings.jitter

        last_exception: BaseException | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await func()
            except retry_on as exc:
                last_exception = exc
                if attempt == attempts:
                    break
                sleep_for = min(delay * (2 ** (attempt - 1)), ceiling)
                if use_jitter:
                    sleep_for = random.uniform(0, sleep_for)
                await asyncio.sleep(sleep_for)

        # Better than an assert: raise directly with a type-safe fallback
        # if somehow it bypassed the loop (e.g., attempts < 1)
        if last_exception is None:
            raise RetryError(
                "Retry loop completed without executing or catching exceptions."
            )
        raise RetryExhaustedError(attempts, last_exception)
