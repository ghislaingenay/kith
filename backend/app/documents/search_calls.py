"""One call to the search store through the retry handler, shared by indexing
and by replaying failed indexing batches."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from core.circuit_breaker.exceptions import CircuitOpenError
from core.retry.exceptions import RetryExhaustedError
from core.retry.handler import RetryHandler
from core.search.exceptions import SearchError, SearchUnavailableError


@dataclass(frozen=True)
class SearchFailure:
    error: str
    attempts: int


async def call_search(
    retry_handler: RetryHandler, func: Callable[[], Awaitable[None]]
) -> SearchFailure | None:
    """Runs one search call through the retry handler; returns how it failed,
    or `None` if it worked. Only the search store being unavailable is
    retried. A request the store rejected would fail the same way again, and
    a call the circuit breaker rejected never reached the store: neither is
    retried, and the second does not count as an attempt."""
    attempts = 0

    async def attempt() -> None:
        nonlocal attempts
        attempts += 1
        await func()

    try:
        await retry_handler.execute(attempt, retry_on=(SearchUnavailableError,))
    except RetryExhaustedError as exc:
        return SearchFailure(str(exc.last_exception), attempts)
    except CircuitOpenError as exc:
        return SearchFailure(str(exc), attempts - 1)
    except SearchError as exc:
        return SearchFailure(str(exc), attempts)
    return None
