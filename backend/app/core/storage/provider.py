"""Abstract interface all storage backends implement."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class StorageObjectMetadata:
    """Metadata returned by `head`, without downloading the object body."""

    size: int
    etag: str
    last_modified: str
    content_type: str | None = None


@dataclass(frozen=True)
class StoragePart:
    """A part already uploaded to a multipart session, as reported by the
    provider (TD-005 §5's `list_parts`)."""

    part_number: int
    etag: str
    size: int


@dataclass(frozen=True)
class CompletedPart:
    """A part number/ETag pair the client supplies to complete a multipart
    upload (TD-005 §5's `complete_multipart_upload`)."""

    part_number: int
    etag: str


class StorageProvider(ABC):
    """Common operations every storage backend (S3, GCS, R2, MinIO) must support."""

    @abstractmethod
    async def upload(
        self,
        key: str,
        stream: AsyncIterator[bytes] | bytes,
        metadata: dict[str, str] | None = None,
        *,
        public: bool = False,
        content_type: str | None = None,
    ) -> str:
        """Upload an object.

        `content_type` sets the object's actual `Content-Type` (what the
        provider serves it as); `metadata` is separate provider-side
        user metadata, not a MIME type.

        Returns the storage key, or — when `public=True` — a stable,
        non-expiring public URL for the object. Never a presigned/signed
        URL with an expiry."""

    @abstractmethod
    def public_url(self, key: str) -> str:
        """The stable, non-expiring public URL an object at `key` has (or
        would have) when stored with `public=True` — the same value
        `upload(..., public=True)` returns, but derivable without a write.
        Does not check whether the object exists."""

    @abstractmethod
    def download(self, key: str) -> AsyncIterator[bytes]:
        """Download an object as a stream of bytes chunks.

        Implementations are async generators — call without `await`, consume
        with `async for chunk in provider.download(key)`.
        """

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete an object. Must not raise if the object does not exist."""

    @abstractmethod
    async def head(self, key: str) -> StorageObjectMetadata:
        """Get object metadata without downloading its body."""

    @abstractmethod
    async def generate_presigned_url(
        self, key: str, method: Literal["GET", "PUT"], ttl: int
    ) -> str:
        """Generate a time-limited presigned URL for direct client access."""

    @abstractmethod
    async def create_multipart_upload(self, key: str) -> str:
        """Start a multipart upload and return the provider's upload id."""

    @abstractmethod
    async def generate_part_upload_url(
        self, key: str, upload_id: str, part_number: int, ttl: int
    ) -> str:
        """Generate a time-limited presigned PUT URL for a single part."""

    @abstractmethod
    async def list_parts(self, key: str, upload_id: str) -> list[StoragePart]:
        """List parts the provider has already received for `upload_id`."""

    @abstractmethod
    async def complete_multipart_upload(
        self, key: str, upload_id: str, parts: list[CompletedPart]
    ) -> str:
        """Assemble the uploaded parts into a single object, returning its key."""

    @abstractmethod
    async def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        """Abort a multipart upload, discarding any parts already received."""
