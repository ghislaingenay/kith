"""Retrieval: the Chunks most relevant to a Query, within one Tenant (ADR-0015)."""

import uuid
from dataclasses import dataclass

from core.circuit_breaker.exceptions import CircuitOpenError
from core.embedding.exceptions import EmbeddingError
from core.embedding.provider import EmbeddingInputType, EmbeddingProvider
from core.logging import setup_logger
from core.rerank.config import RerankSettings
from core.rerank.exceptions import RerankError
from core.rerank.provider import Reranker, RerankResult
from core.search.exceptions import SearchUnavailableError
from core.search.provider import SearchIndex
from documents.config import RetrievalSettings
from documents.exceptions import BlankQueryError
from documents.repository import DocumentsRepository
from documents.schemas import SearchResponse, SearchResultResponse
from documents.text_cleaner import clean_text

logger = setup_logger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    result: SearchResultResponse
    rerank_score: float | None
    """`None` when the Chunk was not reranked."""


@dataclass(frozen=True)
class AskRetrieval:
    """The Chunks an Ask cites, best first. Internal, not an HTTP contract."""

    chunks: list[RetrievedChunk]
    degraded: bool
    """Retrieval fell back to keyword alone (ADR-0015)."""
    is_reranked: bool
    rerank_tokens: int
    """Tokens the reranker used; 0 when not reranked. Not Usage."""


def _clean_query(query: str) -> str:
    """The same cleanup the Chunks went through, so the Query takes the same
    form as the stored text (NFKC, invisible characters, spacing). Raises
    `BlankQueryError` when nothing is left."""
    query = clean_text(query)
    if not query:
        raise BlankQueryError()
    return query


class RetrievalService:
    def __init__(
        self,
        repository: DocumentsRepository,
        search_index: SearchIndex,
        embedding_provider: EmbeddingProvider | None,
        settings: RetrievalSettings,
        reranker: Reranker | None,
        rerank_settings: RerankSettings,
    ) -> None:
        self.repository = repository
        self.search_index = search_index
        self.embedding_provider = embedding_provider
        self.settings = settings
        self.reranker = reranker
        self.rerank_settings = rerank_settings

    async def search(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, query: str
    ) -> SearchResponse:
        """Asks the index for more hits than are shown, then drops those of
        deleted Documents, whose Chunks may still be in the index. Matches by
        keyword and by meaning; without an embedding of the Query (no provider,
        or it failed) it matches by keyword alone and says so with `degraded`.
        The Query text is never logged."""
        query = _clean_query(query)
        query_vector = await self._embed_query(query)
        degraded = query_vector is None
        results = await self._find_live_chunks(
            tenant_id=tenant_id,
            query=query,
            query_vector=query_vector,
            size=self.settings.fetch_size,
        )
        results = results[: self.settings.result_limit]
        logger.info(
            "search_completed",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            result_count=len(results),
            degraded=degraded,
        )
        return SearchResponse(degraded=degraded, results=results)

    async def retrieve_for_ask(
        self,
        *,
        tenant_id: uuid.UUID,
        user_id: uuid.UUID | None,
        query: str,
        rerank: bool | None = None,
    ) -> AskRetrieval:
        """Like `search`, from more candidates, which the reranker narrows to
        the few an Ask cites. Without a reranker (switched off, no Voyage key,
        or it failing) the top ones are kept in Retrieval's order, unscored.
        `rerank` forces Rerank on or off over `RERANK_ENABLED`, from the same
        candidates either way. `user_id` is `None` outside a request (`make
        retrieve`). The Query text is never logged, and Rerank tokens are not
        Usage."""
        query = _clean_query(query)
        query_vector = await self._embed_query(query)
        degraded = query_vector is None
        candidates = await self._find_live_chunks(
            tenant_id=tenant_id,
            query=query,
            query_vector=query_vector,
            size=self.rerank_settings.fetch_size,
        )
        limit = self.rerank_settings.result_limit
        is_rerank_on = self.rerank_settings.enabled if rerank is None else rerank
        reranked = await self._rerank(query, candidates) if is_rerank_on else None
        is_reranked = reranked is not None
        if reranked is None:
            rerank_tokens = 0
            chunks = [RetrievedChunk(result, None) for result in candidates[:limit]]
        else:
            rerank_tokens = reranked.tokens_used
            chunks = [
                RetrievedChunk(candidates[ranked.index], ranked.relevance_score)
                for ranked in reranked.ranking[:limit]
            ]
        logger.info(
            "ask_retrieval_completed",
            tenant_id=str(tenant_id),
            user_id=str(user_id) if user_id else None,
            result_count=len(chunks),
            is_reranked=is_reranked,
            rerank_model=self.rerank_settings.model,
            rerank_tokens=rerank_tokens,
            degraded=degraded,
        )
        if is_reranked:
            logger.debug(
                "ask_retrieval_rerank_scores",
                tenant_id=str(tenant_id),
                rerank_scores=[chunk.rerank_score for chunk in chunks],
            )
        return AskRetrieval(
            chunks=chunks,
            degraded=degraded,
            is_reranked=is_reranked,
            rerank_tokens=rerank_tokens,
        )

    async def _find_live_chunks(
        self,
        *,
        tenant_id: uuid.UUID,
        query: str,
        query_vector: list[float] | None,
        size: int,
    ) -> list[SearchResultResponse]:
        """The Tenant's `size` best hits, best first, less those of deleted
        Documents, whose Chunks may still be in the index, each joined to its
        Document's name and status."""
        try:
            hits = await self.search_index.search_chunks(
                tenant_id=tenant_id,
                query=query,
                query_vector=query_vector,
                size=size,
            )
        except CircuitOpenError as error:
            raise SearchUnavailableError(str(error)) from error
        documents = (
            await self.repository.list_live_documents_by_ids(
                tenant_id=tenant_id, document_ids=[hit.document_id for hit in hits]
            )
            if hits
            else {}
        )
        return [
            SearchResultResponse(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                document_name=document.name,
                document_status=document.ingestion_status,
                page_number=hit.page_number,
                text=hit.text,
                highlights=hit.highlights,
            )
            for hit in hits
            if (document := documents.get(hit.document_id))
        ]

    async def _rerank(
        self, query: str, candidates: list[SearchResultResponse]
    ) -> RerankResult | None:
        """The reranker's ranking of the candidates, or `None` when there is
        none to have: no reranker, no candidates, or the reranker failing,
        slow, or its circuit breaker open (ADR-0015). A failure is a warning,
        not an error: Retrieval's order is still a good one."""
        if self.reranker is None or not candidates:
            return None
        try:
            return await self.reranker.rerank(
                query, [candidate.text for candidate in candidates]
            )
        except (RerankError, CircuitOpenError) as error:
            logger.warning("rerank_failed", error=str(error))
            return None

    async def _embed_query(self, query: str) -> list[float] | None:
        """The Query's vector, or `None` when it cannot be had: no provider,
        the model failing, or its circuit breaker open (ADR-0015)."""
        if self.embedding_provider is None:
            return None
        try:
            result = await self.embedding_provider.embed(
                [query], input_type=EmbeddingInputType.QUERY
            )
        except (EmbeddingError, CircuitOpenError) as error:
            logger.warning("query_embedding_failed", error=str(error))
            return None
        return list(result.vectors[0])
