"""Writing vectors and searching go through the search store's circuit breaker
like every other call (ADR-0013), so a store that is down is not hammered."""

import uuid

import pytest
from core.circuit_breaker.breaker import CircuitBreaker
from core.circuit_breaker.exceptions import CircuitOpenError
from core.search.circuit_breaker_index import CircuitBreakerSearchIndex
from core.search.exceptions import SearchUnavailableError
from core.search.provider import ChunkHit

_TENANT_ID = uuid.uuid4()


class _DownIndex:
    def __init__(self) -> None:
        self.calls = 0

    async def set_chunk_embeddings(self, **_: object) -> list[uuid.UUID]:
        self.calls += 1
        raise SearchUnavailableError("down")

    async def search_chunks(self, **_: object) -> list[ChunkHit]:
        self.calls += 1
        raise SearchUnavailableError("down")


async def test_writing_vectors_fails_fast_once_the_breaker_is_open() -> None:
    down_index = _DownIndex()
    index = CircuitBreakerSearchIndex(
        down_index,
        CircuitBreaker(
            name="search",
            failure_threshold=2,
            reset_timeout_seconds=60,
            failure_types=(SearchUnavailableError,),
            clock=lambda: 0.0,
        ),
    )

    for _ in range(2):
        with pytest.raises(SearchUnavailableError):
            await index.set_chunk_embeddings(tenant_id=_TENANT_ID, embeddings={})
    with pytest.raises(CircuitOpenError):
        await index.set_chunk_embeddings(tenant_id=_TENANT_ID, embeddings={})

    assert down_index.calls == 2


async def test_searching_fails_fast_once_the_breaker_is_open() -> None:
    down_index = _DownIndex()
    index = CircuitBreakerSearchIndex(
        down_index,
        CircuitBreaker(
            name="search",
            failure_threshold=2,
            reset_timeout_seconds=60,
            failure_types=(SearchUnavailableError,),
            clock=lambda: 0.0,
        ),
    )

    for _ in range(2):
        with pytest.raises(SearchUnavailableError):
            await index.search_chunks(tenant_id=_TENANT_ID, query="x", size=1)
    with pytest.raises(CircuitOpenError):
        await index.search_chunks(tenant_id=_TENANT_ID, query="x", size=1)

    assert down_index.calls == 2
