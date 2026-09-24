"""An in-memory `StorageProvider` stand-in that records uploads and deletes
and mints deterministic fake presigned URLs."""

from core.storage.exceptions import StorageError, StorageObjectNotFoundError


class FakeStorageProvider:
    def __init__(self) -> None:
        self.uploaded: list[dict] = []
        self.deleted: list[str] = []
        self.copied: list[tuple[str, str]] = []
        self.keys: set[str] = set()

    async def upload(
        self, key, stream, metadata=None, *, public=False, content_type=None
    ):
        self.uploaded.append(
            {"key": key, "public": public, "content_type": content_type}
        )
        self.keys.add(key)
        return key

    async def upload_file(self, key, path, metadata=None, *, content_type=None):
        return await self.upload(key, b"", metadata, content_type=content_type)

    async def copy(self, source_key, dest_key):
        if source_key not in self.keys:
            raise StorageObjectNotFoundError(source_key)
        self.copied.append((source_key, dest_key))
        self.keys.add(dest_key)

    async def delete(self, key):
        self.deleted.append(key)
        self.keys.discard(key)

    async def generate_presigned_put(
        self, key, ttl, *, content_type, content_length, checksum_sha256=None
    ):
        return f"https://cdn.example.com/{key}?signature=fake&method=PUT"

    async def generate_presigned_url(self, key, method, ttl):
        return f"https://cdn.example.com/{key}?signature=fake&method={method}"


class RaisingStorageProvider(FakeStorageProvider):
    """A storage provider that is down for presigning — everything else
    still works, so an avatar upload can succeed while a later read fails to
    presign it."""

    async def generate_presigned_url(self, key, method, ttl):
        raise StorageError("storage unavailable")
