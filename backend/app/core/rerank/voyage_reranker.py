"""`Reranker` backed by a Voyage reranker, `rerank-3` by default (ADR-0004)."""

from collections.abc import Sequence

from core.rerank.config import RerankSettings
from core.rerank.provider import RankedText, Reranker, RerankResult
from voyageai.client_async import AsyncClient


class VoyageReranker(Reranker):
    def __init__(
        self,
        settings: RerankSettings,
        api_key: str,
        client: AsyncClient | None = None,
    ) -> None:
        self._settings = settings
        # One attempt: the caller decides what to do when Rerank fails.
        self._client = client or AsyncClient(api_key=api_key, max_retries=1)

    async def rerank(self, query: str, texts: Sequence[str]) -> RerankResult:
        response = await self._client.rerank(
            query,
            list(texts),
            model=self._settings.model,
            top_k=self._settings.result_limit,
            truncation=False,
        )
        return RerankResult(
            ranking=[
                RankedText(index=result.index, relevance_score=result.relevance_score)
                for result in response.results
            ],
            tokens_used=response.total_tokens,
        )
