"""Pydantic API schemas for the documents domain."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InitUploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=1024)
    size: int = Field(gt=0)
    content_type: str
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    """Hex SHA-256 of the file, computed by the browser."""


class InitUploadResponse(BaseModel):
    """Where and how the browser sends the file: PUT the bytes to `url` with
    exactly these `headers`, then call finalize."""

    upload_id: uuid.UUID
    url: str
    method: Literal["PUT"] = "PUT"
    headers: dict[str, str]
    expires_in: int


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    size_bytes: int
    page_count: int
    content_hash: str
    ingestion_status: str


class LibraryDocumentResponse(BaseModel):
    """One row of the Uploads Library. `ingestion_stage` and `pages_extracted`
    are null until the worker writes them."""

    id: uuid.UUID
    name: str
    size_bytes: int
    uploader: str
    created_at: datetime
    ingestion_status: str
    ingestion_stage: str | None
    pages_extracted: int | None
    page_count: int


class LibrarySummaryResponse(BaseModel):
    """What the Uploads Library banner needs: Documents still being ingested
    (`uploaded` or `processing`) and Documents whose ingestion `failed`."""

    in_progress: int
    failed: int


class SearchRequest(BaseModel):
    query: str = Field(max_length=1000)


class SearchResultResponse(BaseModel):
    """One retrieved Chunk with its Document. `highlights` are fragments of
    `text`, HTML-escaped, with each match wrapped in `<mark>`."""

    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    document_status: str
    page_number: int
    text: str
    highlights: list[str]


class SearchResponse(BaseModel):
    """`degraded` is true when Retrieval fell back to fewer legs than usual
    (ADR-0015)."""

    degraded: bool
    results: list[SearchResultResponse]
