"""An in-memory `AnswerProvider` stand-in. Streams scripted deltas and token
counts, records every request it receives, and can be scripted to fail
before any output, fail after reporting usage, hit the output cap or be
slow."""

from collections.abc import AsyncIterator, Awaitable, Callable

from core.answer.provider import (
    AnswerDelta,
    AnswerEnd,
    AnswerEnding,
    AnswerProvider,
    AnswerRequest,
    AnswerUsage,
)


class FakeAnswerProvider(AnswerProvider):
    def __init__(self) -> None:
        self.requests: list[AnswerRequest] = []
        self.deltas: list[str] = ["The payment terms are ", "30 days [1]."]
        self.usage: AnswerUsage | None = AnswerUsage(
            input_tokens=2_400, output_tokens=650, reasoning_tokens=200
        )
        """Reported at the end; `None` reports nothing."""
        self.fails_before_output = False
        """End with `failed` and no usage before any delta."""
        self.fails_after_usage = False
        """Stream every delta, then end with `failed` and the usage."""
        self.hits_output_cap = False
        """Stream every delta, then end with `cut_off` and the usage."""
        self.after_delta: Callable[[], Awaitable[None]] | None = None
        """Awaited after each delta, to stand for a slow model."""

    async def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerEnd]:
        self.requests.append(request)
        if self.fails_before_output:
            yield AnswerEnd(AnswerEnding.FAILED, None)
            return
        for text in self.deltas:
            yield AnswerDelta(text)
            if self.after_delta is not None:
                await self.after_delta()
        if self.fails_after_usage:
            yield AnswerEnd(AnswerEnding.FAILED, self.usage)
        elif self.hits_output_cap:
            yield AnswerEnd(AnswerEnding.CUT_OFF, self.usage)
        else:
            yield AnswerEnd(AnswerEnding.COMPLETED, self.usage)
