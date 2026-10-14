"""`AnswerProvider` backed by the OpenAI Responses API (ADR-0016)."""

from collections.abc import AsyncIterator
from typing import cast

import openai
from core.answer.config import AnswerSettings
from core.answer.exceptions import AnswerError, AnswerUnavailableError
from core.answer.provider import (
    AnswerDelta,
    AnswerEnd,
    AnswerEnding,
    AnswerProvider,
    AnswerRequest,
    AnswerUsage,
)
from openai import AsyncOpenAI
from openai.types.responses import Response
from openai.types.shared import ReasoningEffort

ANSWER_TIMEOUT_SECONDS = 60.0


def _is_openai_unavailable(error: openai.APIError) -> bool:
    """Down, slow or overloaded, as opposed to a request OpenAI rejects."""
    if isinstance(error, openai.APIConnectionError):
        return True
    return isinstance(error, openai.APIStatusError) and (
        error.status_code == 429 or error.status_code >= 500
    )


def _usage(response: Response) -> AnswerUsage | None:
    if response.usage is None:
        return None
    return AnswerUsage(
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        reasoning_tokens=response.usage.output_tokens_details.reasoning_tokens,
    )


def _incomplete_ending(response: Response) -> AnswerEnding:
    details = response.incomplete_details
    if details is not None and details.reason == "max_output_tokens":
        return AnswerEnding.CUT_OFF
    return AnswerEnding.FAILED


class OpenAIAnswerProvider(AnswerProvider):
    def __init__(
        self,
        settings: AnswerSettings,
        client: AsyncOpenAI | None = None,
    ) -> None:
        self._settings = settings
        # One attempt: a retried stream could repeat an Answer already shown.
        self._client = client or AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=ANSWER_TIMEOUT_SECONDS,
            max_retries=0,
        )

    async def stream_answer(
        self, request: AnswerRequest
    ) -> AsyncIterator[AnswerDelta | AnswerEnd]:
        try:
            stream = await self._client.responses.create(
                model=self._settings.model,
                reasoning={
                    "effort": cast(ReasoningEffort, self._settings.reasoning_effort)
                },
                instructions=request.instructions,
                input=request.prompt,
                max_output_tokens=self._settings.max_output_tokens,
                # No breakpoints: each Ask's passages differ, so a cache
                # write would be paid for and never read.
                prompt_cache_options={"mode": "explicit"},
                store=False,
                stream=True,
            )
            try:
                async for event in stream:
                    if event.type == "response.output_text.delta":
                        yield AnswerDelta(event.delta)
                    elif event.type == "response.completed":
                        yield AnswerEnd(AnswerEnding.COMPLETED, _usage(event.response))
                        return
                    elif event.type == "response.incomplete":
                        yield AnswerEnd(
                            _incomplete_ending(event.response), _usage(event.response)
                        )
                        return
                    elif event.type == "response.failed":
                        yield AnswerEnd(AnswerEnding.FAILED, _usage(event.response))
                        return
            finally:
                # Stops the model when the reader stops early.
                await stream.close()
        except openai.APIError as error:
            if _is_openai_unavailable(error):
                raise AnswerUnavailableError(f"Answer failed: {error}") from error
            raise AnswerError(f"Answer was rejected: {error}") from error
        raise AnswerUnavailableError("The Answer's stream ended before it finished")
