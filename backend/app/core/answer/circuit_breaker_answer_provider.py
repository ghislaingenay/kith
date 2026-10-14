"""An `AnswerProvider` that sends every Answer through one circuit breaker
(ADR-0013's pattern, as for the reranker), so a model that is down costs at
most one failed call per breaker cycle instead of one per Ask. The breaker is
injected; the composition root decides which errors count as failures."""

from collections.abc import AsyncIterator
from contextlib import aclosing

from core.answer.exceptions import AnswerUnavailableError
from core.answer.provider import AnswerDelta, AnswerEnd, AnswerProvider, AnswerRequest
from core.circuit_breaker.breaker import CircuitBreaker
from core.circuit_breaker.exceptions import CircuitOpenError


class CircuitBreakerAnswerProvider(AnswerProvider):
    def __init__(self, provider: AnswerProvider, breaker: CircuitBreaker) -> None:
        self._provider = provider
        self._breaker = breaker

    async def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerEnd]:
        """The whole stream is one call. An open breaker raises
        `AnswerUnavailableError`, as a model that cannot be reached does."""
        try:
            async with (
                self._breaker.guard(),
                aclosing(self._provider.stream_answer(request)) as parts,
            ):
                async for part in parts:
                    yield part
        except CircuitOpenError as error:
            raise AnswerUnavailableError(str(error)) from error
