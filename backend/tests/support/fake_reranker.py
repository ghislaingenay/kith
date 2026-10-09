"""An in-memory `Reranker` stand-in. Returns a scripted order and scores, and
records every request it receives."""

from collections.abc import Sequence

from core.rerank.provider import RankedText, Reranker, RerankResult


class FakeReranker(Reranker):
    def __init__(self) -> None:
        self.requests: list[tuple[str, list[str]]] = []
        """The Query and texts of each call, in order."""
        self.scores: dict[str, float] = {}
        """Score given to a text; the fake ranks by it, highest first, and an
        unlisted text scores 0."""
        self.tokens_used = 11

    async def rerank(self, query: str, texts: Sequence[str]) -> RerankResult:
        self.requests.append((query, list(texts)))
        ranking = sorted(
            (
                RankedText(index=index, relevance_score=self.scores.get(text, 0.0))
                for index, text in enumerate(texts)
            ),
            key=lambda ranked: ranked.relevance_score,
            reverse=True,
        )
        return RerankResult(ranking=ranking, tokens_used=self.tokens_used)
