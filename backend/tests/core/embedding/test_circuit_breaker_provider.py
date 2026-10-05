"""The `embedding` breaker around the embedding provider (ADR-0013's pattern,
ADR-0014): the real breaker, on a fake clock, around a scripted fake
provider. It is its own breaker, separate from the `search` one."""

import uuid

import pytest
from core.circuit_breaker.breaker import CircuitBreaker
from core.circuit_breaker.exceptions import CircuitOpenError
from core.container import Container
from core.embedding.circuit_breaker_provider import CircuitBreakerEmbeddingProvider
from core.embedding.exceptions import EmbeddingError, EmbeddingUnavailableError
from core.embedding.provider import EmbeddingInputType
from core.search.circuit_breaker_index import CircuitBreakerSearchIndex
from core.search.exceptions import SearchUnavailableError

from tests.support.fake_embedding_provider import FakeEmbeddingProvider
from tests.support.fake_search_index import FakeSearchIndex


def _embedding_breaker() -> CircuitBreaker:
    return CircuitBreaker(
        name="embedding",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(EmbeddingUnavailableError,),
        clock=lambda: 0.0,
    )


async def _embed(provider: CircuitBreakerEmbeddingProvider) -> None:
    await provider.embed(["some text"], input_type=EmbeddingInputType.DOCUMENT)


async def test_calls_pass_through_to_the_provider() -> None:
    fake = FakeEmbeddingProvider()
    provider = CircuitBreakerEmbeddingProvider(fake, _embedding_breaker())

    result = await provider.embed(["a b c"], input_type=EmbeddingInputType.DOCUMENT)

    assert result.tokens_used == 3
    assert fake.input_types == [EmbeddingInputType.DOCUMENT]
    assert await provider.count_tokens(["a b c"]) == [3]


async def test_five_unavailable_failures_open_the_breaker_and_later_calls_fail_fast() -> (
    None
):
    fake = FakeEmbeddingProvider()
    fake.is_down = True
    provider = CircuitBreakerEmbeddingProvider(fake, _embedding_breaker())

    for _ in range(5):
        with pytest.raises(EmbeddingUnavailableError):
            await _embed(provider)
    with pytest.raises(CircuitOpenError) as opened:
        await _embed(provider)

    assert opened.value.service == "embedding"
    assert fake.embed_calls == 5


async def test_rejected_requests_do_not_open_the_breaker() -> None:
    fake = FakeEmbeddingProvider()
    fake.rejected_texts = {"some text"}
    provider = CircuitBreakerEmbeddingProvider(fake, _embedding_breaker())

    for _ in range(10):
        with pytest.raises(EmbeddingError):
            await _embed(provider)
    fake.rejected_texts = set()
    await _embed(provider)

    assert fake.embed_calls == 11


async def test_an_open_embedding_breaker_does_not_stop_the_search_index() -> None:
    fake_embedding = FakeEmbeddingProvider()
    fake_embedding.is_down = True
    embedding = CircuitBreakerEmbeddingProvider(fake_embedding, _embedding_breaker())
    search_breaker = CircuitBreaker(
        name="search",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(SearchUnavailableError,),
        clock=lambda: 0.0,
    )
    search_index = CircuitBreakerSearchIndex(FakeSearchIndex(), search_breaker)
    for _ in range(5):
        with pytest.raises(EmbeddingUnavailableError):
            await _embed(embedding)

    with pytest.raises(CircuitOpenError):
        await _embed(embedding)
    missing = await search_index.set_chunk_embeddings(
        tenant_id=uuid.uuid4(), embeddings={}
    )

    assert missing == []


def test_the_container_builds_an_embedding_breaker_separate_from_the_search_one() -> (
    None
):
    container = Container()

    embedding_breaker = container.embedding_circuit_breaker()
    search_breaker = container.search_circuit_breaker()

    assert embedding_breaker is not search_breaker
    assert embedding_breaker is container.embedding_circuit_breaker()
