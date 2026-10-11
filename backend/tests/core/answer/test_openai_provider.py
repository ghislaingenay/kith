"""How `OpenAIAnswerProvider` talks to OpenAI, against a stub client: the real
API is never called by automated tests."""

from collections.abc import AsyncIterator

import httpx2
import openai
import pytest
from core.answer.config import AnswerSettings
from core.answer.exceptions import AnswerError, AnswerUnavailableError
from core.answer.openai_provider import OpenAIAnswerProvider
from core.answer.provider import (
    AnswerDelta,
    AnswerEnd,
    AnswerEnding,
    AnswerRequest,
    AnswerUsage,
)
from openai.types.responses import (
    Response,
    ResponseCompletedEvent,
    ResponseFailedEvent,
    ResponseIncompleteEvent,
    ResponseTextDeltaEvent,
    ResponseUsage,
)
from openai.types.responses.response import IncompleteDetails
from openai.types.responses.response_usage import (
    InputTokensDetails,
    OutputTokensDetails,
)

_REQUEST = AnswerRequest(instructions="Answer from the passages.", prompt="<question>")
_USAGE = ResponseUsage(
    input_tokens=2_400,
    input_tokens_details=InputTokensDetails(cached_tokens=0, cache_write_tokens=0),
    output_tokens=650,
    output_tokens_details=OutputTokensDetails(reasoning_tokens=200),
    total_tokens=3_050,
)
_ANSWER_USAGE = AnswerUsage(input_tokens=2_400, output_tokens=650, reasoning_tokens=200)
"""What `_USAGE` reads as."""
_REQUEST_URL = httpx2.Request("POST", "https://api.openai.com/v1/responses")


def _delta(text: str) -> ResponseTextDeltaEvent:
    return ResponseTextDeltaEvent.model_construct(
        type="response.output_text.delta", delta=text
    )


def _completed(usage: ResponseUsage | None = _USAGE) -> ResponseCompletedEvent:
    return ResponseCompletedEvent.model_construct(
        type="response.completed",
        response=Response.model_construct(status="completed", usage=usage),
    )


def _incomplete(reason: str) -> ResponseIncompleteEvent:
    return ResponseIncompleteEvent.model_construct(
        type="response.incomplete",
        response=Response.model_construct(
            status="incomplete",
            usage=_USAGE,
            incomplete_details=IncompleteDetails(reason=reason),
        ),
    )


def _failed(usage: ResponseUsage | None) -> ResponseFailedEvent:
    return ResponseFailedEvent.model_construct(
        type="response.failed",
        response=Response.model_construct(status="failed", usage=usage),
    )


def _status_error(status_code: int) -> openai.APIStatusError:
    response = httpx2.Response(status_code, request=_REQUEST_URL)
    return openai.APIStatusError("refused", response=response, body=None)


class _StubResponses:
    def __init__(
        self,
        events: list[object],
        *,
        create_error: Exception | None,
        stream_error: Exception | None,
    ) -> None:
        self.events = events
        self.create_error = create_error
        self.stream_error = stream_error
        self.create_calls: list[dict[str, object]] = []

    async def create(self, **options: object) -> AsyncIterator[object]:
        self.create_calls.append(options)
        if self.create_error is not None:
            raise self.create_error
        return self._stream()

    async def _stream(self) -> AsyncIterator[object]:
        for event in self.events:
            yield event
        if self.stream_error is not None:
            raise self.stream_error


class _StubClient:
    def __init__(
        self,
        events: list[object] | None = None,
        *,
        create_error: Exception | None = None,
        stream_error: Exception | None = None,
    ) -> None:
        self.responses = _StubResponses(
            events if events is not None else [_completed()],
            create_error=create_error,
            stream_error=stream_error,
        )


def _provider(client: _StubClient) -> OpenAIAnswerProvider:
    settings = AnswerSettings(
        model="gpt-6-luna",
        reasoning_effort="low",
        max_output_tokens=8_000,
        openai_api_key="key",
    )
    return OpenAIAnswerProvider(settings, client)  # type: ignore[arg-type]


async def _collect(provider: OpenAIAnswerProvider) -> list[AnswerDelta | AnswerEnd]:
    return [part async for part in provider.stream_answer(_REQUEST)]


async def test_the_request_carries_the_configured_model_effort_cap_and_no_caching() -> (
    None
):
    client = _StubClient()

    await _collect(_provider(client))

    assert client.responses.create_calls == [
        {
            "model": "gpt-6-luna",
            "reasoning": {"effort": "low"},
            "instructions": "Answer from the passages.",
            "input": "<question>",
            "max_output_tokens": 8_000,
            "prompt_cache_options": {"mode": "explicit"},
            "store": False,
            "stream": True,
        }
    ]


async def test_text_deltas_pass_through_then_the_completion_with_its_usage() -> None:
    client = _StubClient(
        [_delta("The payment terms are "), _delta("30 days [1]."), _completed()]
    )

    parts = await _collect(_provider(client))

    assert parts == [
        AnswerDelta("The payment terms are "),
        AnswerDelta("30 days [1]."),
        AnswerEnd(
            AnswerEnding.COMPLETED,
            _ANSWER_USAGE,
        ),
    ]


async def test_a_completion_without_usage_reports_none() -> None:
    parts = await _collect(_provider(_StubClient([_completed(usage=None)])))

    assert parts == [AnswerEnd(AnswerEnding.COMPLETED, None)]


async def test_an_answer_stopped_at_the_output_cap_is_cut_off() -> None:
    parts = await _collect(
        _provider(_StubClient([_delta("Half an"), _incomplete("max_output_tokens")]))
    )

    assert parts[-1] == AnswerEnd(
        AnswerEnding.CUT_OFF,
        _ANSWER_USAGE,
    )


async def test_an_answer_stopped_for_another_reason_failed() -> None:
    parts = await _collect(_provider(_StubClient([_incomplete("content_filter")])))

    assert parts == [
        AnswerEnd(
            AnswerEnding.FAILED,
            _ANSWER_USAGE,
        )
    ]


async def test_a_response_the_model_failed_ends_failed_with_what_it_reported() -> None:
    parts = await _collect(_provider(_StubClient([_failed(usage=None)])))

    assert parts == [AnswerEnd(AnswerEnding.FAILED, None)]


@pytest.mark.parametrize(
    "error",
    [
        openai.APITimeoutError(request=_REQUEST_URL),
        openai.APIConnectionError(request=_REQUEST_URL),
        _status_error(429),
        _status_error(500),
        _status_error(503),
    ],
)
async def test_a_model_that_is_down_or_busy_is_reported_as_unavailable(
    error: Exception,
) -> None:
    with pytest.raises(AnswerUnavailableError):
        await _collect(_provider(_StubClient(create_error=error)))


async def test_a_stream_that_breaks_partway_is_reported_as_unavailable() -> None:
    client = _StubClient(
        [_delta("Half an")],
        stream_error=openai.APIConnectionError(request=_REQUEST_URL),
    )

    with pytest.raises(AnswerUnavailableError):
        await _collect(_provider(client))


async def test_a_stream_that_ends_without_a_final_event_is_reported_as_unavailable() -> (
    None
):
    with pytest.raises(AnswerUnavailableError):
        await _collect(_provider(_StubClient([_delta("Half an")])))


@pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422])
async def test_a_request_the_model_rejects_is_not_reported_as_unavailable(
    status_code: int,
) -> None:
    with pytest.raises(AnswerError) as raised:
        await _collect(_provider(_StubClient(create_error=_status_error(status_code))))

    assert not isinstance(raised.value, AnswerUnavailableError)
