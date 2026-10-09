"""An in-memory `Reranker` stand-in. Returns a scripted order and scores,
records every request it receives, and can be scripted to fail the way a
reranker that is down, slow or that rejects the request does."""

from collections.abc import Awaitable, Callable, Sequence

from core.rerank.exceptions import RerankError, RerankUnavailableError
from core.rerank.provider import RankedText, Reranker, RerankResult


class FakeReranker(Reranker):
    def __init__(self) -> None:
        self.requests: list[tuple[str, list[str]]] = []
        """The Query and texts of each call, in order."""
        self.scores: dict[str, float] = {}
        """Score given to a text; the fake ranks by it, highest first, and an
        unlisted text scores 0."""
        self.tokens_used = 11
        self.is_down = False
        """Raise `RerankUnavailableError`, as a reranker that is down does."""
        self.rejects = False
        """Raise `RerankError`, as a reranker that refuses the request does."""
        self.after_rerank: Callable[[], Awaitable[None]] | None = None
        """Awaited before answering, to stand for a slow reranker."""

    async def rerank(self, query: str, texts: Sequence[str]) -> RerankResult:
        self.requests.append((query, list(texts)))
        if self.is_down:
            raise RerankUnavailableError("fake reranker is down")
        if self.rejects:
            raise RerankError("fake reranker rejected the request")
        if self.after_rerank is not None:
            await self.after_rerank()
        ranking = sorted(
            (
                RankedText(index=index, relevance_score=self.scores.get(text, 0.0))
                for index, text in enumerate(texts)
            ),
            key=lambda ranked: ranked.relevance_score,
            reverse=True,
        )
        return RerankResult(ranking=ranking, tokens_used=self.tokens_used)
