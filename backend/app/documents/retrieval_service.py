"""Retrieval: the Chunks most relevant to a Query, within one Tenant (ADR-0015)."""

import uuid

from core.circuit_breaker.exceptions import CircuitOpenError
from core.embedding.exceptions import EmbeddingError
from core.embedding.provider import EmbeddingInputType, EmbeddingProvider
from core.logging import setup_logger
from core.search.exceptions import SearchUnavailableError
from core.search.provider import SearchIndex
from documents.config import RetrievalSettings
from documents.exceptions import BlankQueryError
from documents.repository import DocumentsRepository
from documents.schemas import SearchResponse, SearchResultResponse
from documents.text_cleaner import clean_text

logger = setup_logger(__name__)


class RetrievalService:
    def __init__(
        self,
        repository: DocumentsRepository,
        search_index: SearchIndex,
        embedding_provider: EmbeddingProvider | None,
        settings: RetrievalSettings,
    ) -> None:
        self.repository = repository
        self.search_index = search_index
        self.embedding_provider = embedding_provider
        self.settings = settings

    async def search(
        self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, query: str
    ) -> SearchResponse:
        """Asks the index for more hits than are shown, then drops those of
        deleted Documents, whose Chunks may still be in the index. Matches by
        keyword and by meaning; without an embedding of the Query (no provider,
        or it failed) it matches by keyword alone and says so with `degraded`.
        The Query text is never logged."""
        # The same cleanup the Chunks went through, so the Query takes the
        # same form as the stored text (NFKC, invisible characters, spacing).
        query = clean_text(query)
        if not query:
            raise BlankQueryError()
        query_vector = await self._embed_query(query)
        degraded = query_vector is None
        try:
            hits = await self.search_index.search_chunks(
                tenant_id=tenant_id,
                query=query,
                query_vector=query_vector,
                size=self.settings.fetch_size,
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
        results = [
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
        ][: self.settings.result_limit]
        logger.info(
            "search_completed",
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            result_count=len(results),
            degraded=degraded,
        )
        return SearchResponse(degraded=degraded, results=results)

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
