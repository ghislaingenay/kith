from pathlib import Path

import pytest

from core.storage.exceptions import StorageObjectNotFoundError
from tests.support.fake_storage import FakeStorageProvider

_SOURCE_KEY = "pending/a"
_DEST_KEY = "tenants/t/a.pdf"


async def test_copy_records_the_copy_and_keeps_the_source() -> None:
    storage = FakeStorageProvider()
    await storage.upload(_SOURCE_KEY, b"x")

    await storage.copy(_SOURCE_KEY, _DEST_KEY)

    assert storage.copied == [(_SOURCE_KEY, _DEST_KEY)]
    assert _SOURCE_KEY in storage.keys
    assert _DEST_KEY in storage.keys


async def test_copy_missing_source_raises_not_found() -> None:
    storage = FakeStorageProvider()

    with pytest.raises(StorageObjectNotFoundError):
        await storage.copy("missing", _DEST_KEY)


async def test_delete_removes_the_key() -> None:
    storage = FakeStorageProvider()
    await storage.upload(_SOURCE_KEY, b"x")

    await storage.delete(_SOURCE_KEY)

    assert _SOURCE_KEY not in storage.keys


async def test_upload_file_records_the_upload(tmp_path: Path) -> None:
    storage = FakeStorageProvider()
    source = tmp_path / "a.pdf"
    source.write_bytes(b"x")

    await storage.upload_file(_SOURCE_KEY, source, content_type="application/pdf")

    assert _SOURCE_KEY in storage.keys
    assert storage.uploaded[-1]["content_type"] == "application/pdf"


async def test_generate_presigned_put_returns_a_fake_url() -> None:
    storage = FakeStorageProvider()

    url = await storage.generate_presigned_put(
        _SOURCE_KEY, ttl=60, content_type="application/pdf", content_length=1
    )

    assert _SOURCE_KEY in url
