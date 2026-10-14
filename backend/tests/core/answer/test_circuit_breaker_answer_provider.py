"""The `answer` breaker and the time limit around the answer model (ADR-0013's
pattern, as for the reranker): the real breaker, on a fake clock, around the
fake answer provider. An open breaker fails like an unavailable model."""

import asyncio

import pytest
from core.answer.circuit_breaker_answer_provider import CircuitBreakerAnswerProvider
from core.answer.exceptions import AnswerError, AnswerUnavailableError
from core.answer.provider import (
    AnswerDelta,
    AnswerEnd,
    AnswerEnding,
    AnswerProvider,
    AnswerRequest,
)
from core.answer.time_limited_answer_provider import TimeLimitedAnswerProvider
from core.circuit_breaker.breaker import CircuitBreaker
from core.container import Container

from tests.support.fake_answer_provider import FakeAnswerProvider

_TIME_LIMIT_SECONDS = 0.05
_REQUEST = AnswerRequest(instructions="Answer.", prompt="<question>q</question>")


def _answer_breaker() -> CircuitBreaker:
    return CircuitBreaker(
        name="answer",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(AnswerUnavailableError,),
        clock=lambda: 0.0,
    )


async def _answer(provider: AnswerProvider) -> list[AnswerDelta | AnswerEnd]:
    return [part async for part in provider.stream_answer(_REQUEST)]


async def test_the_answer_streams_through_the_breaker() -> None:
    fake = FakeAnswerProvider()
    provider = CircuitBreakerAnswerProvider(fake, _answer_breaker())

    parts = await _answer(provider)

    assert parts == [
        AnswerDelta("The payment terms are "),
        AnswerDelta("30 days [1]."),
        AnswerEnd(AnswerEnding.COMPLETED, fake.usage),
    ]
    assert fake.requests == [_REQUEST]


async def test_five_unavailable_failures_open_the_breaker_and_later_answers_fail_fast() -> (
    None
):
    fake = FakeAnswerProvider()
    fake.error = AnswerUnavailableError("down")
    provider = CircuitBreakerAnswerProvider(fake, _answer_breaker())

    for _ in range(5):
        with pytest.raises(AnswerUnavailableError):
            await _answer(provider)
    # Failed like an unavailable model, without reaching it.
    with pytest.raises(AnswerUnavailableError, match="answer"):
        await _answer(provider)

    assert len(fake.requests) == 5


async def test_rejected_requests_do_not_open_the_breaker() -> None:
    fake = FakeAnswerProvider()
    fake.error = AnswerError("bad key")
    provider = CircuitBreakerAnswerProvider(fake, _answer_breaker())

    for _ in range(10):
        with pytest.raises(AnswerError):
            await _answer(provider)
    fake.error = None
    await _answer(provider)

    assert len(fake.requests) == 11


async def test_a_reader_that_stops_early_does_not_count_against_the_model() -> None:
    fake = FakeAnswerProvider()
    breaker = _answer_breaker()
    provider = CircuitBreakerAnswerProvider(fake, breaker)

    for _ in range(10):
        stream = provider.stream_answer(_REQUEST)
        await anext(stream)
        await stream.aclose()

    assert len(await _answer(provider)) == 3


async def test_an_answer_over_the_time_limit_counts_as_the_model_being_unavailable() -> (
    None
):
    fake = FakeAnswerProvider()
    fake.deltas = ["a", "b", "c", "d"]

    # Each delta is within the limit; the whole Answer is not.
    async def _slow_delta() -> None:
        await asyncio.sleep(_TIME_LIMIT_SECONDS * 0.6)

    fake.after_delta = _slow_delta
    limited = TimeLimitedAnswerProvider(fake, timeout_seconds=_TIME_LIMIT_SECONDS)

    with pytest.raises(AnswerUnavailableError):
        await _answer(limited)


async def test_an_answer_within_the_time_limit_streams_through() -> None:
    fake = FakeAnswerProvider()
    limited = TimeLimitedAnswerProvider(fake, timeout_seconds=_TIME_LIMIT_SECONDS)

    parts = await _answer(limited)

    assert parts[-1] == AnswerEnd(AnswerEnding.COMPLETED, fake.usage)


async def test_time_the_reader_takes_does_not_count_against_the_limit() -> None:
    fake = FakeAnswerProvider()
    fake.after_delta = lambda: asyncio.sleep(0)
    limited = TimeLimitedAnswerProvider(fake, timeout_seconds=_TIME_LIMIT_SECONDS)

    parts = []
    async for part in limited.stream_answer(_REQUEST):
        parts.append(part)
        await asyncio.sleep(_TIME_LIMIT_SECONDS)

    assert parts[-1] == AnswerEnd(AnswerEnding.COMPLETED, fake.usage)


async def test_slow_answers_open_the_breaker_when_limited_inside_it() -> None:
    fake = FakeAnswerProvider()

    async def _slower_than_the_time_limit() -> None:
        await asyncio.sleep(1)

    fake.after_delta = _slower_than_the_time_limit
    provider = CircuitBreakerAnswerProvider(
        TimeLimitedAnswerProvider(fake, timeout_seconds=_TIME_LIMIT_SECONDS),
        _answer_breaker(),
    )

    for _ in range(5):
        with pytest.raises(AnswerUnavailableError):
            await _answer(provider)
    with pytest.raises(AnswerUnavailableError):
        await _answer(provider)

    assert len(fake.requests) == 5


def test_the_container_builds_an_answer_breaker_separate_from_the_others() -> None:
    container = Container()

    answer_breaker = container.answer_circuit_breaker()

    assert answer_breaker is container.answer_circuit_breaker()
    assert answer_breaker is not container.rerank_circuit_breaker()
    assert answer_breaker is not container.search_circuit_breaker()
    assert answer_breaker is not container.embedding_circuit_breaker()
