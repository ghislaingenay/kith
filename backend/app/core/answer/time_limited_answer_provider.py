"""An `AnswerProvider` that gives up on a slow Answer (ADR-0016)."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import aclosing

from core.answer.exceptions import AnswerUnavailableError
from core.answer.provider import AnswerDelta, AnswerEnd, AnswerProvider, AnswerRequest


class TimeLimitedAnswerProvider(AnswerProvider):
    """Gives up on an Answer that takes longer than `timeout_seconds` in all,
    as the model being unavailable, so the circuit breaker around it counts a
    slow model like a down one. Only time spent waiting on the model counts,
    not time the reader takes between parts."""

    def __init__(self, provider: AnswerProvider, timeout_seconds: float) -> None:
        self._provider = provider
        self._timeout_seconds = timeout_seconds

    async def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerEnd]:
        clock = asyncio.get_running_loop().time
        remaining = self._timeout_seconds
        async with aclosing(self._provider.stream_answer(request)) as parts:
            while True:
                started = clock()
                try:
                    async with asyncio.timeout(remaining):
                        part = await anext(parts)
                except StopAsyncIteration:
                    return
                except TimeoutError as error:
                    raise AnswerUnavailableError(
                        f"The Answer took longer than {self._timeout_seconds}s"
                    ) from error
                remaining -= clock() - started
                yield part
