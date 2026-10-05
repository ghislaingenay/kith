"""The `embed_document` job (ADR-0014): adds vectors to the Chunks of a
Document that are already in the search index. It reads the Chunk text kept
in Postgres, never the PDF, and can be run again without embedding anything
twice."""

import uuid
from collections.abc import Sequence

from core.embedding.provider import EmbeddingInputType, EmbeddingProvider
from core.logging import setup_logger
from core.search.provider import SearchIndex
from documents.config import IngestionSettings
from documents.exceptions import DocumentNotFoundError
from documents.ingestion_status import set_status_after_embedding
from documents.models import Chunk, IngestionStage, IngestionStatus
from documents.repository import DocumentsRepository

logger = setup_logger(__name__)


async def embed_document(ctx: dict, *, document_id: str, tenant_id: str) -> None:
    session_factory = ctx["db_session_factory"]
    settings: IngestionSettings = ctx["ingestion_settings"]
    search_index: SearchIndex = ctx["search_index"]
    embedding_provider: EmbeddingProvider = ctx["embedding_provider"]
    async with session_factory() as session:
        repository = DocumentsRepository(session)
        try:
            document = await repository.get_document(uuid.UUID(document_id))
        except DocumentNotFoundError:
            logger.warning(
                "embed_document_missing", document_id=document_id, tenant_id=tenant_id
            )
            return

        if str(document.tenant_id) != tenant_id:
            logger.warning(
                "embed_document_tenant_mismatch",
                document_id=document_id,
                tenant_id=tenant_id,
                document_tenant_id=str(document.tenant_id),
            )
            return

        is_waiting_at_embedding = (
            document.ingestion_status == IngestionStatus.PROCESSING
            and document.ingestion_stage == IngestionStage.EMBEDDING
        )
        if (
            not is_waiting_at_embedding
            and document.ingestion_status != IngestionStatus.PARTIAL
        ):
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

        tokens_used = 0
        if chunks:
            token_counts = await embedding_provider.count_tokens(
                [chunk.text for chunk in chunks]
            )
            for batch in _group_into_requests(
                chunks,
                token_counts,
                token_cap=settings.embed_batch_token_cap,
                max_chunks=settings.embed_batch_max_chunks,
            ):
                result = await embedding_provider.embed(
                    [chunk.text for chunk in batch],
                    input_type=EmbeddingInputType.DOCUMENT,
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
                        document_id=document_id,
                        chunks=len(missing_chunk_ids),
                    )
                await repository.mark_chunks_embedded(
                    [chunk.id for chunk in batch if chunk.id not in missing_chunk_ids]
                )
                await session.commit()

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


def _group_into_requests(
    chunks: Sequence[Chunk],
    token_counts: Sequence[int],
    *,
    token_cap: int,
    max_chunks: int,
) -> list[list[Chunk]]:
    """Consecutive Chunks whose combined token count stays within the cap. A
    Chunk over the cap on its own gets a request to itself: the model, not
    this job, refuses it."""
    requests: list[list[Chunk]] = []
    request_tokens = 0
    for chunk, token_count in zip(chunks, token_counts, strict=True):
        fits = (
            requests
            and request_tokens + token_count <= token_cap
            and len(requests[-1]) < max_chunks
        )
        if not fits:
            requests.append([])
            request_tokens = 0
        requests[-1].append(chunk)
        request_tokens += token_count
    return requests
