"""One call to the embedding model through the retry handler (ADR-0014)."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from core.circuit_breaker.exceptions import CircuitOpenError
from core.embedding.exceptions import EmbeddingError, EmbeddingUnavailableError
from core.embedding.provider import EmbeddingResult
from core.retry.exceptions import RetryExhaustedError
from core.retry.handler import RetryHandler


@dataclass(frozen=True)
class EmbeddingFailure:
    error: str
    attempts: int


async def call_embedding(
    retry_handler: RetryHandler, func: Callable[[], Awaitable[EmbeddingResult]]
) -> EmbeddingResult | EmbeddingFailure:
    """Runs one embedding request through the retry handler; returns the
    result, or how it failed. Only the model being unavailable is retried. A
    request the model rejected would fail the same way again, and a call the
    circuit breaker rejected never reached the model: neither is retried, and
    the second does not count as an attempt."""
    attempts = 0

    async def attempt() -> EmbeddingResult:
        nonlocal attempts
        attempts += 1
        return await func()

    try:
        return await retry_handler.execute(
            attempt, retry_on=(EmbeddingUnavailableError,)
        )
    except RetryExhaustedError as exc:
        return EmbeddingFailure(str(exc.last_exception), attempts)
    except CircuitOpenError as exc:
        return EmbeddingFailure(str(exc), attempts - 1)
    except EmbeddingError as exc:
        return EmbeddingFailure(str(exc), attempts)
