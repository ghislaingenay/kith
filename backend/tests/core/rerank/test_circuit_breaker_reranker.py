"""The `rerank` breaker and the time limit around the reranker (ADR-0013's
pattern, ADR-0015): the real breaker, on a fake clock, around the fake
reranker. It is its own breaker, separate from `search` and `embedding`."""

import asyncio

import pytest
from core.circuit_breaker.breaker import CircuitBreaker
from core.circuit_breaker.exceptions import CircuitOpenError
from core.container import Container
from core.rerank.circuit_breaker_reranker import CircuitBreakerReranker
from core.rerank.exceptions import RerankError, RerankUnavailableError
from core.rerank.provider import Reranker
from core.rerank.time_limited_reranker import TimeLimitedReranker

from tests.support.fake_reranker import FakeReranker

_TIME_LIMIT_SECONDS = 0.01


async def _slower_than_the_time_limit() -> None:
    await asyncio.sleep(1)


def _rerank_breaker() -> CircuitBreaker:
    return CircuitBreaker(
        name="rerank",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(RerankUnavailableError,),
        clock=lambda: 0.0,
    )


async def _rerank(reranker: Reranker) -> None:
    await reranker.rerank("q", ["some text"])


async def test_calls_pass_through_to_the_reranker() -> None:
    fake = FakeReranker()
    fake.scores = {"b": 0.9}
    reranker = CircuitBreakerReranker(fake, _rerank_breaker())

    result = await reranker.rerank("q", ["a", "b"])

    assert [ranked.index for ranked in result.ranking] == [1, 0]
    assert fake.requests == [("q", ["a", "b"])]


async def test_five_unavailable_failures_open_the_breaker_and_later_calls_fail_fast() -> (
    None
):
    fake = FakeReranker()
    fake.is_down = True
    reranker = CircuitBreakerReranker(fake, _rerank_breaker())

    for _ in range(5):
        with pytest.raises(RerankUnavailableError):
            await _rerank(reranker)
    with pytest.raises(CircuitOpenError) as opened:
        await _rerank(reranker)

    assert opened.value.service == "rerank"
    assert len(fake.requests) == 5


async def test_rejected_requests_do_not_open_the_breaker() -> None:
    fake = FakeReranker()
    fake.rejects = True
    reranker = CircuitBreakerReranker(fake, _rerank_breaker())

    for _ in range(10):
        with pytest.raises(RerankError):
            await _rerank(reranker)
    fake.rejects = False
    await _rerank(reranker)

    assert len(fake.requests) == 11


async def test_a_request_over_the_time_limit_counts_as_the_reranker_being_unavailable() -> (
    None
):
    fake = FakeReranker()
    fake.after_rerank = _slower_than_the_time_limit
    limited = TimeLimitedReranker(fake, timeout_seconds=_TIME_LIMIT_SECONDS)

    with pytest.raises(RerankUnavailableError):
        await _rerank(limited)


async def test_slow_requests_open_the_breaker_when_limited_inside_it() -> None:
    fake = FakeReranker()
    fake.after_rerank = _slower_than_the_time_limit
    reranker = CircuitBreakerReranker(
        TimeLimitedReranker(fake, timeout_seconds=_TIME_LIMIT_SECONDS),
        _rerank_breaker(),
    )

    for _ in range(5):
        with pytest.raises(RerankUnavailableError):
            await _rerank(reranker)
    with pytest.raises(CircuitOpenError):
        await _rerank(reranker)

    assert len(fake.requests) == 5


def test_the_container_builds_a_rerank_breaker_separate_from_the_others() -> None:
    container = Container()

    rerank_breaker = container.rerank_circuit_breaker()

    assert rerank_breaker is container.rerank_circuit_breaker()
    assert rerank_breaker is not container.search_circuit_breaker()
    assert rerank_breaker is not container.embedding_circuit_breaker()
