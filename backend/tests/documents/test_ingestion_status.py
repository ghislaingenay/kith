"""Ingestion Status after embedding is derived from both Chunk statuses
(ADR-0014): a Chunk is searchable only when it is indexed and embedded."""

import pytest
from documents.ingestion_status import set_status_after_embedding
from documents.models import Chunk, ChunkStatus, Document, IngestionStatus

DONE, PENDING, FAILED = ChunkStatus.DONE, ChunkStatus.PENDING, ChunkStatus.FAILED


def _chunk(indexing: ChunkStatus, embedding: ChunkStatus) -> Chunk:
    return Chunk(indexing_status=indexing, embedding_status=embedding)


def _status_after(*chunks: Chunk) -> IngestionStatus:
    document = Document(ingestion_status=IngestionStatus.PROCESSING)
    set_status_after_embedding(document, chunks)
    return IngestionStatus(document.ingestion_status)


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        ([(DONE, DONE), (DONE, DONE)], IngestionStatus.READY),
        ([(DONE, DONE), (DONE, FAILED)], IngestionStatus.PARTIAL),
        ([(DONE, DONE), (FAILED, PENDING)], IngestionStatus.PARTIAL),
        ([(DONE, FAILED), (DONE, FAILED)], IngestionStatus.FAILED),
        ([(DONE, FAILED), (FAILED, PENDING)], IngestionStatus.FAILED),
        ([(FAILED, PENDING), (FAILED, PENDING)], IngestionStatus.FAILED),
        # Still waiting for a vector: left as it is.
        ([(DONE, DONE), (DONE, PENDING)], IngestionStatus.PROCESSING),
    ],
)
def test_status_is_derived_from_indexing_and_embedding_together(
    chunks: list[tuple[ChunkStatus, ChunkStatus]], expected: IngestionStatus
) -> None:
    assert _status_after(*(_chunk(*pair) for pair in chunks)) == expected
