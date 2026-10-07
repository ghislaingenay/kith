"""How `OpenSearchIndex` sorts the store's failures: the ones worth retrying
(and counting towards the circuit breaker) from the ones that would fail the
same way again."""

import uuid

import pytest
from core.search.config import SearchSettings
from core.search.exceptions import SearchError, SearchUnavailableError
from core.search.opensearch_index import OpenSearchIndex
from core.search.provider import ChunkDocument
from opensearchpy import helpers
from opensearchpy.exceptions import (
    ConnectionError as OpenSearchConnectionError,
    ConnectionTimeout,
    RequestError,
    TransportError,
)

_CHUNK = ChunkDocument(
    id=uuid.uuid4(),
    tenant_id=uuid.uuid4(),
    document_id=uuid.uuid4(),
    page_number=1,
    ordinal=0,
    text="text",
)


class _StubClient:
    def __init__(self, error: Exception) -> None:
        self._error = error

    async def delete_by_query(self, **_: object) -> None:
        raise self._error

    async def search(self, **_: object) -> None:
        raise self._error


def _index_failing_with(error: Exception) -> OpenSearchIndex:
    index = OpenSearchIndex(SearchSettings(search_url="http://localhost:9200"))
    index._client = _StubClient(error)  # type: ignore[assignment]
    return index


@pytest.mark.parametrize(
    "error",
    [
        OpenSearchConnectionError("N/A", "refused", Exception("refused")),
        ConnectionTimeout("N/A", "timed out", Exception("timed out")),
        TransportError(503, "unavailable"),
        TransportError(429, "too many requests"),
    ],
)
async def test_an_unreachable_or_overloaded_store_is_unavailable(
    error: Exception,
) -> None:
    index = _index_failing_with(error)

    with pytest.raises(SearchUnavailableError):
        await index.delete_document_chunks(
            tenant_id=_CHUNK.tenant_id, document_id=_CHUNK.document_id
        )
    with pytest.raises(SearchUnavailableError):
        await index.search_chunks(tenant_id=_CHUNK.tenant_id, query="x", size=1)


async def test_a_rejected_request_is_a_search_error_that_is_not_unavailable() -> None:
    index = _index_failing_with(RequestError(400, "mapper_parsing_exception"))

    with pytest.raises(SearchError) as raised:
        await index.delete_document_chunks(
            tenant_id=_CHUNK.tenant_id, document_id=_CHUNK.document_id
        )

    assert not isinstance(raised.value, SearchUnavailableError)


@pytest.mark.parametrize(
    ("status", "expected"),
    [(429, SearchUnavailableError), (503, SearchUnavailableError)],
)
async def test_bulk_items_the_store_could_not_take_right_now_are_unavailable(
    monkeypatch: pytest.MonkeyPatch, status: int, expected: type[Exception]
) -> None:
    index = _index_failing_with(Exception())

    async def failing_bulk(*_: object, **__: object) -> None:
        raise helpers.BulkIndexError("1 failed", [{"index": {"status": status}}])

    monkeypatch.setattr(helpers, "async_bulk", failing_bulk)

    with pytest.raises(expected):
        await index.index_chunks([_CHUNK])


async def test_bulk_items_the_store_rejected_are_not_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    index = _index_failing_with(Exception())

    async def failing_bulk(*_: object, **__: object) -> None:
        raise helpers.BulkIndexError("1 failed", [{"index": {"status": 400}}])

    monkeypatch.setattr(helpers, "async_bulk", failing_bulk)

    with pytest.raises(SearchError) as raised:
        await index.index_chunks([_CHUNK])

    assert not isinstance(raised.value, SearchUnavailableError)


async def test_a_query_vector_is_refused_until_the_meaning_leg_exists() -> None:
    index = _index_failing_with(Exception())

    with pytest.raises(NotImplementedError):
        await index.search_chunks(
            tenant_id=_CHUNK.tenant_id, query="x", query_vector=[0.1], size=1
        )
