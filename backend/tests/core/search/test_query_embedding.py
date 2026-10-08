import asyncio

import pytest
from core.embedding.exceptions import EmbeddingUnavailableError
from core.embedding.provider import EmbeddingInputType
from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.circuit_breaker_provider import CircuitBreakerEmbeddingProvider
from core.search.query_embedding import (
    TimeLimitedEmbeddingProvider,
    create_query_embedding_provider,
)

from tests.support.fake_embedding_provider import FakeEmbeddingProvider


def _breaker() -> CircuitBreaker:
    return CircuitBreaker(
        name="embedding",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(),
    )


def test_no_provider_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "")

    assert create_query_embedding_provider(_breaker()) is None


def test_a_provider_behind_the_breaker_with_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    provider = create_query_embedding_provider(_breaker())

    assert isinstance(provider, CircuitBreakerEmbeddingProvider)


async def test_a_request_over_the_time_limit_counts_as_the_model_being_unavailable() -> (
    None
):
    provider = FakeEmbeddingProvider()

    async def slow() -> None:
        await asyncio.sleep(1)

    provider.after_embed = slow
    limited = TimeLimitedEmbeddingProvider(provider, timeout_seconds=0.01)

    with pytest.raises(EmbeddingUnavailableError):
        await limited.embed(["x"], input_type=EmbeddingInputType.QUERY)
