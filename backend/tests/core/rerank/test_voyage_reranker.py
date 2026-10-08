"""How `VoyageReranker` talks to Voyage, against a stub client: the real API
is never called by automated tests."""

from types import SimpleNamespace

from core.rerank.config import RerankSettings
from core.rerank.provider import RankedText, RerankResult
from core.rerank.voyage_reranker import VoyageReranker
from voyageai.object.reranking import RerankingObject


class _StubClient:
    def __init__(self, ranking: list[tuple[int, float]]) -> None:
        self.ranking = ranking
        self.rerank_calls: list[dict] = []

    async def rerank(
        self, query: str, documents: list[str], **options: object
    ) -> RerankingObject:
        self.rerank_calls.append({"query": query, "documents": documents, **options})
        response = SimpleNamespace(
            data=[
                SimpleNamespace(index=index, relevance_score=score)
                for index, score in self.ranking
            ],
            usage=SimpleNamespace(total_tokens=42),
        )
        return RerankingObject(documents, response)


def _reranker(client: _StubClient) -> VoyageReranker:
    return VoyageReranker(
        RerankSettings(model="rerank-test", result_limit=2), "key", client
    )


async def test_texts_are_reranked_with_the_configured_options() -> None:
    client = _StubClient([(1, 0.9), (0, 0.4)])

    await _reranker(client).rerank("the query", ["first", "second", "third"])

    assert client.rerank_calls == [
        {
            "query": "the query",
            "documents": ["first", "second", "third"],
            "model": "rerank-test",
            "top_k": 2,
            "truncation": False,
        }
    ]


async def test_the_response_becomes_indices_and_scores_best_first_with_tokens() -> None:
    client = _StubClient([(2, 0.9), (0, 0.4)])

    result = await _reranker(client).rerank("q", ["first", "second", "third"])

    assert result == RerankResult(
        ranking=[
            RankedText(index=2, relevance_score=0.9),
            RankedText(index=0, relevance_score=0.4),
        ],
        tokens_used=42,
    )
