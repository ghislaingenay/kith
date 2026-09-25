"""Pydantic API schemas for the documents domain."""

import uuid
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
