from collections.abc import AsyncIterator, Iterator
from unittest.mock import patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from core.storage.exceptions import (
    StorageError,
    StorageObjectNotFoundError,
    StoragePermissionError,
)
from core.storage.provider import CompletedPart
from core.storage.s3_provider import S3StorageProvider


def _client_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, "operation")


_BUCKET = "test-bucket"
_REGION = "us-east-1"
_KEY = "originals/test.txt"


@pytest.fixture()
def s3_provider() -> Iterator[S3StorageProvider]:
    with mock_aws():
        boto3.client("s3", region_name=_REGION).create_bucket(Bucket=_BUCKET)
        yield S3StorageProvider(bucket=_BUCKET, region=_REGION)


async def _read_all(stream: AsyncIterator[bytes]) -> bytes:
    return b"".join([chunk async for chunk in stream])


async def test_upload_and_download_roundtrip(s3_provider: S3StorageProvider) -> None:
    await s3_provider.upload(_KEY, b"hello world", metadata={"mime_type": "text/plain"})

    body = await _read_all(s3_provider.download(_KEY))

    assert body == b"hello world"


async def test_upload_returns_key_by_default(s3_provider: S3StorageProvider) -> None:
    returned = await s3_provider.upload(_KEY, b"hello world")

    assert returned == _KEY


async def test_upload_public_returns_virtual_hosted_url_without_custom_endpoint(
    s3_provider: S3StorageProvider,
) -> None:
    returned = await s3_provider.upload(_KEY, b"hello world", public=True)

    assert returned == f"https://{_BUCKET}.s3.{_REGION}.amazonaws.com/{_KEY}"


async def test_upload_public_prefers_configured_public_base_url() -> None:
    with mock_aws():
        boto3.client("s3", region_name=_REGION).create_bucket(Bucket=_BUCKET)
        provider = S3StorageProvider(
            bucket=_BUCKET,
            region=_REGION,
            public_base_url="https://cdn.example.com/assets",
        )

        returned = await provider.upload(_KEY, b"hello world", public=True)

    assert returned == f"https://cdn.example.com/assets/{_KEY}"


def test_public_url_falls_back_to_path_style_endpoint_url() -> None:
    """No live MinIO/R2 server is available here (mirrors
    `test_accepts_custom_endpoint_url`'s wiring-only check) — this exercises
    URL construction directly rather than a real upload."""
    provider = S3StorageProvider(
        bucket=_BUCKET, region=_REGION, endpoint_url="http://localhost:9000"
    )

    assert provider._public_url(_KEY) == f"http://localhost:9000/{_BUCKET}/{_KEY}"


async def test_upload_accepts_async_iterator(s3_provider: S3StorageProvider) -> None:
    async def chunks() -> AsyncIterator[bytes]:
        yield b"chunk-1-"
        yield b"chunk-2"

    await s3_provider.upload(_KEY, chunks())

    body = await _read_all(s3_provider.download(_KEY))

    assert body == b"chunk-1-chunk-2"


async def test_head_returns_metadata(s3_provider: S3StorageProvider) -> None:
    await s3_provider.upload(_KEY, b"12345")

    metadata = await s3_provider.head(_KEY)

    assert metadata.size == 5
    assert metadata.etag
    assert metadata.last_modified


async def test_head_missing_key_raises_not_found(
    s3_provider: S3StorageProvider,
) -> None:
    with pytest.raises(StorageObjectNotFoundError):
        await s3_provider.head("missing")


async def test_download_missing_key_raises_not_found(
    s3_provider: S3StorageProvider,
) -> None:
    with pytest.raises(StorageObjectNotFoundError):
        await _read_all(s3_provider.download("missing"))


async def test_delete_removes_object(s3_provider: S3StorageProvider) -> None:
    await s3_provider.upload(_KEY, b"bye")

    await s3_provider.delete(_KEY)

    with pytest.raises(StorageObjectNotFoundError):
        await s3_provider.head(_KEY)


async def test_delete_is_idempotent_for_missing_key(
    s3_provider: S3StorageProvider,
) -> None:
    await s3_provider.delete("does-not-exist")


async def test_generate_presigned_url_get(s3_provider: S3StorageProvider) -> None:
    url = await s3_provider.generate_presigned_url(_KEY, "GET", ttl=60)

    assert url.startswith("http")
    assert _BUCKET in url


async def test_generate_presigned_url_put(s3_provider: S3StorageProvider) -> None:
    url = await s3_provider.generate_presigned_url(_KEY, "PUT", ttl=60)

    assert url.startswith("http")
    assert _BUCKET in url


async def test_upload_wraps_permission_denied(s3_provider: S3StorageProvider) -> None:
    with (
        patch.object(
            s3_provider._client,
            "upload_fileobj",
            side_effect=_client_error("AccessDenied"),
        ),
        pytest.raises(StoragePermissionError) as exc_info,
    ):
        await s3_provider.upload(_KEY, b"data")

    assert exc_info.value.key == _KEY


async def test_upload_wraps_unrecognized_error_as_generic_storage_error(
    s3_provider: S3StorageProvider,
) -> None:
    with (
        patch.object(
            s3_provider._client,
            "upload_fileobj",
            side_effect=_client_error("InternalError"),
        ),
        pytest.raises(StorageError) as exc_info,
    ):
        await s3_provider.upload(_KEY, b"data")

    assert not isinstance(exc_info.value, StorageObjectNotFoundError)
    assert not isinstance(exc_info.value, StoragePermissionError)


async def test_delete_wraps_permission_denied(s3_provider: S3StorageProvider) -> None:
    with (
        patch.object(
            s3_provider._client,
            "delete_object",
            side_effect=_client_error("AccessDenied"),
        ),
        pytest.raises(StoragePermissionError) as exc_info,
    ):
        await s3_provider.delete(_KEY)

    assert exc_info.value.key == _KEY


async def test_generate_presigned_url_wraps_client_error(
    s3_provider: S3StorageProvider,
) -> None:
    with (
        patch.object(
            s3_provider._client,
            "generate_presigned_url",
            side_effect=_client_error("InternalError"),
        ),
        pytest.raises(StorageError) as exc_info,
    ):
        await s3_provider.generate_presigned_url(_KEY, "GET", ttl=60)

    assert not isinstance(exc_info.value, StoragePermissionError)


def test_accepts_custom_endpoint_url() -> None:
    """Wiring check only — no live MinIO/R2 server is available in this environment."""
    endpoint = "http://localhost:9000"

    provider = S3StorageProvider(bucket=_BUCKET, region=_REGION, endpoint_url=endpoint)

    assert provider._client.meta.endpoint_url == endpoint


async def test_create_multipart_upload_returns_upload_id(
    s3_provider: S3StorageProvider,
) -> None:
    upload_id = await s3_provider.create_multipart_upload(_KEY)

    assert upload_id


async def test_generate_part_upload_url(s3_provider: S3StorageProvider) -> None:
    upload_id = await s3_provider.create_multipart_upload(_KEY)

    url = await s3_provider.generate_part_upload_url(_KEY, upload_id, 1, ttl=60)

    assert url.startswith("http")
    assert _BUCKET in url
    assert upload_id in url


async def test_list_parts_returns_uploaded_parts(
    s3_provider: S3StorageProvider,
) -> None:
    upload_id = await s3_provider.create_multipart_upload(_KEY)
    # Simulate the client's direct PUT to a part URL — the presigned URL
    # itself targets the same underlying object the raw client call does,
    # so uploading via the boto3 client is equivalent for test purposes
    # (mirrors how `tests/upload/test_router.py`'s end-to-end test simulates
    # a client PUT via the provider rather than an actual HTTP request).
    part_response = s3_provider._client.upload_part(
        Bucket=_BUCKET, Key=_KEY, UploadId=upload_id, PartNumber=1, Body=b"x" * 1024
    )

    parts = await s3_provider.list_parts(_KEY, upload_id)

    assert len(parts) == 1
    assert parts[0].part_number == 1
    assert parts[0].etag == part_response["ETag"].strip('"')
    assert parts[0].size == 1024


async def test_list_parts_returns_empty_before_any_part_uploaded(
    s3_provider: S3StorageProvider,
) -> None:
    upload_id = await s3_provider.create_multipart_upload(_KEY)

    parts = await s3_provider.list_parts(_KEY, upload_id)

    assert parts == []


async def test_complete_multipart_upload_assembles_parts(
    s3_provider: S3StorageProvider,
) -> None:
    upload_id = await s3_provider.create_multipart_upload(_KEY)
    part_response = s3_provider._client.upload_part(
        Bucket=_BUCKET, Key=_KEY, UploadId=upload_id, PartNumber=1, Body=b"x" * 1024
    )

    returned_key = await s3_provider.complete_multipart_upload(
        _KEY,
        upload_id,
        [CompletedPart(part_number=1, etag=part_response["ETag"].strip('"'))],
    )

    assert returned_key == _KEY
    metadata = await s3_provider.head(_KEY)
    assert metadata.size == 1024


async def test_abort_multipart_upload_discards_parts(
    s3_provider: S3StorageProvider,
) -> None:
    upload_id = await s3_provider.create_multipart_upload(_KEY)
    s3_provider._client.upload_part(
        Bucket=_BUCKET, Key=_KEY, UploadId=upload_id, PartNumber=1, Body=b"x" * 1024
    )

    await s3_provider.abort_multipart_upload(_KEY, upload_id)

    with pytest.raises(StorageError):
        await s3_provider.list_parts(_KEY, upload_id)


async def test_create_multipart_upload_wraps_client_error(
    s3_provider: S3StorageProvider,
) -> None:
    with (
        patch.object(
            s3_provider._client,
            "create_multipart_upload",
            side_effect=_client_error("InternalError"),
        ),
        pytest.raises(StorageError) as exc_info,
    ):
        await s3_provider.create_multipart_upload(_KEY)

    assert not isinstance(exc_info.value, StoragePermissionError)
