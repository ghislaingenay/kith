"""Presigned-PUT behaviour against a real MinIO (testcontainers). moto does
not enforce signed headers, so this is the only place that proves a wrong
length or a missing signed header is actually rejected by the store."""

import base64
import hashlib
import uuid
from collections.abc import Iterator

import boto3
import httpx
import pytest
from testcontainers.community.minio import MinioContainer

from core.storage.exceptions import StorageObjectNotFoundError
from core.storage.s3_provider import S3StorageProvider

_BUCKET = "uploads"
_REGION = "us-east-1"
_PDF = b"%PDF-1.7 minio"
_PDF_TYPE = "application/pdf"
_HEADERS = {"Content-Type": _PDF_TYPE}


@pytest.fixture(scope="module")
def _minio() -> Iterator[MinioContainer]:
    try:
        with MinioContainer(image="quay.io/minio/minio:latest") as minio:
            yield minio
    except Exception as exc:  # noqa: BLE001 — testcontainers raises whatever
        # the docker SDK gives it; any of them means "no usable Docker here".
        pytest.skip(f"Docker not available — skipping MinIO integration tests: {exc}")


@pytest.fixture(scope="module")
def _endpoint(_minio: MinioContainer) -> str:
    config = _minio.get_config()
    endpoint = f"http://{config['endpoint']}"
    boto3.client(
        "s3",
        region_name=_REGION,
        endpoint_url=endpoint,
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
    ).create_bucket(Bucket=_BUCKET)
    return endpoint


@pytest.fixture
def provider(
    _minio: MinioContainer, _endpoint: str, monkeypatch: pytest.MonkeyPatch
) -> S3StorageProvider:
    config = _minio.get_config()
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", config["access_key"])
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", config["secret_key"])
    # boto3's default session caches the credentials it first resolved; drop
    # any picked up by earlier tests so these env vars are the ones used.
    boto3.setup_default_session()
    return S3StorageProvider(bucket=_BUCKET, region=_REGION, endpoint_url=_endpoint)


@pytest.fixture
def key() -> str:
    return f"pending/tenant-1/{uuid.uuid4()}"


async def _presigned_put(provider: S3StorageProvider, key: str) -> str:
    return await provider.generate_presigned_put(
        key, ttl=60, content_type=_PDF_TYPE, content_length=len(_PDF)
    )


async def test_matching_put_succeeds(provider: S3StorageProvider, key: str) -> None:
    url = await _presigned_put(provider, key)

    async with httpx.AsyncClient() as client:
        response = await client.put(url, content=_PDF, headers=_HEADERS)

    assert response.status_code == 200
    head = await provider.head(key)
    assert head.size == len(_PDF)
    assert head.content_type == _PDF_TYPE


async def test_wrong_length_put_is_rejected(
    provider: S3StorageProvider, key: str
) -> None:
    url = await _presigned_put(provider, key)

    async with httpx.AsyncClient() as client:
        response = await client.put(url, content=_PDF + b"extra", headers=_HEADERS)

    assert 400 <= response.status_code < 500
    with pytest.raises(StorageObjectNotFoundError):
        await provider.head(key)


async def test_put_missing_a_signed_header_is_rejected(
    provider: S3StorageProvider, key: str
) -> None:
    url = await _presigned_put(provider, key)

    async with httpx.AsyncClient() as client:
        response = await client.put(url, content=_PDF)

    assert 400 <= response.status_code < 500
    with pytest.raises(StorageObjectNotFoundError):
        await provider.head(key)


async def test_signed_checksum_put_needs_the_matching_header(
    provider: S3StorageProvider, key: str
) -> None:
    checksum = base64.b64encode(hashlib.sha256(_PDF).digest()).decode()
    url = await provider.generate_presigned_put(
        key,
        ttl=60,
        content_type=_PDF_TYPE,
        content_length=len(_PDF),
        checksum_sha256=checksum,
    )

    async with httpx.AsyncClient() as client:
        without_header = await client.put(url, content=_PDF, headers=_HEADERS)
        with_header = await client.put(
            url,
            content=_PDF,
            headers={**_HEADERS, "x-amz-checksum-sha256": checksum},
        )

    assert 400 <= without_header.status_code < 500
    assert with_header.status_code == 200
