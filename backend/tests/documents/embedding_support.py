"""Helpers the embedding tests share: a Document at `embedding` with its
Chunks already in the (fake) search index, and reading the rows back."""

import hashlib
import uuid
from collections.abc import Sequence

from core.search.provider import ChunkDocument
from documents.models import (
    Chunk,
    ChunkStatus,
    Document,
    IngestionStage,
    IngestionStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tests.documents.conftest import Caller
from tests.support.fake_search_index import FakeSearchIndex


async def document_waiting_at_embedding(
    db_session: AsyncSession,
    search_index: FakeSearchIndex,
    caller: Caller,
    chunk_texts: Sequence[str],
) -> uuid.UUID:
    """A Document whose Chunks are all indexed, as indexing leaves it."""
    document = Document(
        tenant_id=caller.tenant_id,
        uploader_id=caller.user_id,
        name="report.pdf",
        size_bytes=1,
        page_count=1,
        content_hash=uuid.uuid4().hex,
        storage_key="unused",
        ingestion_status=IngestionStatus.PROCESSING,
        ingestion_stage=IngestionStage.EMBEDDING,
    )
    db_session.add(document)
    await db_session.flush()
    for ordinal, text in enumerate(chunk_texts):
        chunk = Chunk(
            document_id=document.id,
            tenant_id=caller.tenant_id,
            page_number=1,
            ordinal=ordinal,
            text=text,
            text_hash=hashlib.sha256(text.encode()).hexdigest(),
            token_count=len(text.split()),
            indexing_status=ChunkStatus.DONE,
        )
        db_session.add(chunk)
        await db_session.flush()
        search_index.indexed.append(
            ChunkDocument(
                id=chunk.id,
                tenant_id=caller.tenant_id,
                document_id=document.id,
                page_number=1,
                ordinal=ordinal,
                text=text,
            )
        )
    await db_session.commit()
    return document.id


async def load_document(db_session: AsyncSession, document_id: uuid.UUID) -> Document:
    db_session.expire_all()
    return (
        await db_session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one()


async def load_chunks(db_session: AsyncSession, document_id: uuid.UUID) -> list[Chunk]:
    db_session.expire_all()
    return list(
        (
            await db_session.execute(
                select(Chunk)
                .where(Chunk.document_id == document_id)
                .order_by(Chunk.ordinal)
            )
        ).scalars()
    )
