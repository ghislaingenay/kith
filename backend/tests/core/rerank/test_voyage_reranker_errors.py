"""How `VoyageReranker` reports a Voyage failure, against a stub client: the
same unavailable-or-rejected split as the Voyage embedding provider."""

import pytest
from core.rerank.config import RerankSettings
from core.rerank.exceptions import RerankError, RerankUnavailableError
from core.rerank.voyage_reranker import VoyageReranker
from voyageai import error as voyage_error
from voyageai.object.reranking import RerankingObject


class _FailingClient:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def rerank(
        self, query: str, documents: list[str], **options: object
    ) -> RerankingObject:
        raise self.error


async def _rerank(error: Exception) -> None:
    reranker = VoyageReranker(RerankSettings(), "key", _FailingClient(error))  # type: ignore[arg-type]
    await reranker.rerank("q", ["text"])


@pytest.mark.parametrize(
    "error",
    [
        voyage_error.Timeout("timed out"),
        voyage_error.APIConnectionError("connection reset"),
        voyage_error.RateLimitError("slow down", http_status=429),
        voyage_error.ServerError("boom", http_status=500),
        voyage_error.ServiceUnavailableError("overloaded", http_status=503),
        voyage_error.APIError("bad gateway page", http_status=520),
    ],
)
async def test_a_reranker_that_is_down_or_busy_is_reported_as_unavailable(
    error: Exception,
) -> None:
    with pytest.raises(RerankUnavailableError):
        await _rerank(error)


@pytest.mark.parametrize(
    "error",
    [
        voyage_error.InvalidRequestError("too many documents", http_status=400),
        voyage_error.AuthenticationError("bad key", http_status=401),
        voyage_error.MalformedRequestError("malformed", http_status=422),
        voyage_error.APIError("unexpected", http_status=418),
    ],
)
async def test_a_request_the_reranker_rejects_is_not_reported_as_unavailable(
    error: Exception,
) -> None:
    with pytest.raises(RerankError) as raised:
        await _rerank(error)

    assert not isinstance(raised.value, RerankUnavailableError)
