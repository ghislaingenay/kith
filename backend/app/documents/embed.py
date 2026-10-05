"""The `embed_document` job (ADR-0014): adds vectors to the Chunks of a
Document that are already in the search index. It reads the Chunk text kept
in Postgres, never the PDF, and can be run again without embedding anything
twice."""

from collections.abc import Sequence

from core.embedding.provider import EmbeddingInputType, EmbeddingProvider
from core.logging import setup_logger
from core.search.provider import SearchIndex
from documents.config import IngestionSettings
from documents.ingestion_status import (
    is_waiting_for_vectors,
    set_status_after_embedding,
)
from documents.job_documents import load_document_for_job
from documents.models import Chunk, Document
from documents.repository import DocumentsRepository

logger = setup_logger(__name__)


async def embed_document(ctx: dict, *, document_id: str, tenant_id: str) -> None:
    session_factory = ctx["db_session_factory"]
    settings: IngestionSettings = ctx["ingestion_settings"]
    search_index: SearchIndex = ctx["search_index"]
    embedding_provider: EmbeddingProvider = ctx["embedding_provider"]
    async with session_factory() as session:
        repository = DocumentsRepository(session)
        document = await load_document_for_job(
            repository,
            job="embed_document",
            document_id=document_id,
            tenant_id=tenant_id,
        )
        if document is None:
            return

        if not is_waiting_for_vectors(document):
            logger.info(
                "embed_document_skipped",
                document_id=document_id,
                ingestion_status=document.ingestion_status,
                ingestion_stage=document.ingestion_stage,
            )
            return

        chunks = list(await repository.list_chunks_pending_embedding(document.id))
        # Ends the read transaction, so none is held open during the calls to
        # the embedding model.
        await session.commit()

        tokens_used = await _embed_chunks(
            repository, document, chunks, search_index, embedding_provider, settings
        )

        set_status_after_embedding(document, await repository.list_chunks(document.id))
        await session.commit()
        logger.info(
            "embed_document_embedded",
            document_id=document_id,
            tenant_id=tenant_id,
            chunks=len(chunks),
            tokens_used=tokens_used,
            ingestion_status=document.ingestion_status,
        )


async def _embed_chunks(
    repository: DocumentsRepository,
    document: Document,
    chunks: Sequence[Chunk],
    search_index: SearchIndex,
    embedding_provider: EmbeddingProvider,
    settings: IngestionSettings,
) -> int:
    """Embeds the Chunks in token-capped requests, writing each request's
    vectors to the index and marking its Chunks embedded before the next one.
    Returns the tokens the model reported. A Chunk the index no longer holds
    is logged and left pending."""
    if not chunks:
        return 0
    token_counts = await embedding_provider.count_tokens(
        [chunk.text for chunk in chunks]
    )
    tokens_used = 0
    for batch in _group_into_batches(
        chunks,
        token_counts,
        token_cap=settings.embed_batch_token_cap,
        max_chunks=settings.embed_batch_max_chunks,
    ):
        result = await embedding_provider.embed(
            [chunk.text for chunk in batch], input_type=EmbeddingInputType.DOCUMENT
        )
        tokens_used += result.tokens_used
        missing_chunk_ids = set(
            await search_index.set_chunk_embeddings(
                tenant_id=document.tenant_id,
                embeddings={
                    chunk.id: vector
                    for chunk, vector in zip(batch, result.vectors, strict=True)
                },
            )
        )
        if missing_chunk_ids:
            logger.warning(
                "embed_document_chunks_not_in_index",
                document_id=str(document.id),
                chunks=len(missing_chunk_ids),
            )
        await repository.mark_chunks_embedded(
            [chunk.id for chunk in batch if chunk.id not in missing_chunk_ids]
        )
        await repository.session.commit()
    return tokens_used


def _group_into_batches(
    chunks: Sequence[Chunk],
    token_counts: Sequence[int],
    *,
    token_cap: int,
    max_chunks: int,
) -> list[list[Chunk]]:
    """Consecutive Chunks whose combined token count stays within the cap. A
    Chunk over the cap on its own gets a batch to itself: the model, not
    this job, refuses it."""
    batches: list[list[Chunk]] = []
    batch_tokens = 0
    for chunk, token_count in zip(chunks, token_counts, strict=True):
        fits_current_batch = (
            bool(batches)
            and batch_tokens + token_count <= token_cap
            and len(batches[-1]) < max_chunks
        )
        if not fits_current_batch:
            batches.append([])
            batch_tokens = 0
        batches[-1].append(chunk)
        batch_tokens += token_count
    return batches
