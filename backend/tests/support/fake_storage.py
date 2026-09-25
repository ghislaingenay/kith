"""An in-memory `StorageProvider` stand-in that records uploads and deletes
and mints deterministic fake presigned URLs."""

from collections.abc import AsyncIterator

from core.storage.exceptions import StorageError, StorageObjectNotFoundError
from core.storage.provider import StorageObjectMetadata


class FakeStorageProvider:
    def __init__(self) -> None:
        self.uploaded: list[dict] = []
        self.deleted: list[str] = []
        self.copied: list[tuple[str, str]] = []
        self.keys: set[str] = set()
        self.objects: dict[str, bytes] = {}
        self.presigned_puts: list[dict] = []

    def put_object(self, key: str, data: bytes) -> None:
        """Stand in for a browser PUT straight to storage."""
        self.objects[key] = data
        self.keys.add(key)

    async def upload(
        self, key, stream, metadata=None, *, public=False, content_type=None
    ):
        self.uploaded.append(
            {"key": key, "public": public, "content_type": content_type}
        )
        if isinstance(stream, bytes):
            self.put_object(key, stream)
        else:
            self.put_object(key, b"".join([chunk async for chunk in stream]))
        return key

    async def upload_file(self, key, path, metadata=None, *, content_type=None):
        return await self.upload(
            key, path.read_bytes(), metadata, content_type=content_type
        )

    async def copy(self, source_key, dest_key):
        if source_key not in self.keys:
            raise StorageObjectNotFoundError(source_key)
        self.copied.append((source_key, dest_key))
        self.put_object(dest_key, self.objects.get(source_key, b""))

    async def head(self, key) -> StorageObjectMetadata:
        if key not in self.keys:
            raise StorageObjectNotFoundError(key)
        return StorageObjectMetadata(
            size=len(self.objects.get(key, b"")), etag="fake", last_modified="fake"
        )

    async def download(self, key) -> AsyncIterator[bytes]:
        if key not in self.keys:
            raise StorageObjectNotFoundError(key)
        data = self.objects.get(key, b"")
        for start in range(0, len(data), 1024):
            yield data[start : start + 1024]

    async def delete(self, key):
        self.deleted.append(key)
        self.keys.discard(key)
        self.objects.pop(key, None)

    async def generate_presigned_put(
        self, key, ttl, *, content_type, content_length, checksum_sha256=None
    ):
        self.presigned_puts.append(
            {
                "key": key,
                "ttl": ttl,
                "content_type": content_type,
                "content_length": content_length,
                "checksum_sha256": checksum_sha256,
            }
        )
        return f"https://cdn.example.com/{key}?signature=fake&method=PUT"

    async def generate_presigned_url(self, key, method, ttl):
        return f"https://cdn.example.com/{key}?signature=fake&method={method}"


class RaisingStorageProvider(FakeStorageProvider):
    """A storage provider that is down for presigning — everything else
    still works, so an avatar upload can succeed while a later read fails to
    presign it."""

    async def generate_presigned_url(self, key, method, ttl):
        raise StorageError("storage unavailable")
