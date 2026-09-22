"""An in-memory `StorageProvider` stand-in that records uploads and deletes
and mints deterministic fake presigned URLs."""

from core.storage.exceptions import StorageError


class FakeStorageProvider:
    def __init__(self) -> None:
        self.uploaded: list[dict] = []
        self.deleted: list[str] = []

    async def upload(
        self, key, stream, metadata=None, *, public=False, content_type=None
    ):
        self.uploaded.append(
            {"key": key, "public": public, "content_type": content_type}
        )
        return key

    async def delete(self, key):
        self.deleted.append(key)

    async def generate_presigned_url(self, key, method, ttl):
        return f"https://cdn.example.com/{key}?signature=fake&method={method}"


class RaisingStorageProvider(FakeStorageProvider):
    """A storage provider that is down for presigning — everything else
    still works, so an avatar upload can succeed while a later read fails to
    presign it."""

    async def generate_presigned_url(self, key, method, ttl):
        raise StorageError("storage unavailable")
