from types import SimpleNamespace
from typing import Any

import pytest

from core.storage.exceptions import StorageConfigurationError
from core.storage.factory import StorageProviderFactory
from core.storage.s3_provider import S3StorageProvider

_BUCKET = "uploads"
_REGION = "us-east-1"
_ENDPOINT = "http://localhost:9000"


def _settings(**overrides: Any) -> SimpleNamespace:
    defaults = {
        "provider": "s3",
        "s3_bucket": _BUCKET,
        "s3_region": _REGION,
        "s3_endpoint": None,
        "s3_public_endpoint": None,
        "public_base_url": None,
    }
    return SimpleNamespace(**{**defaults, **overrides})


@pytest.mark.parametrize("provider_name", ["s3", "minio", "r2"])
def test_create_returns_s3_provider_for_s3_compatible_backends(
    provider_name: str,
) -> None:
    provider = StorageProviderFactory.create(_settings(provider=provider_name))

    assert isinstance(provider, S3StorageProvider)


def test_create_passes_custom_endpoint_through() -> None:
    provider = StorageProviderFactory.create(
        _settings(provider="minio", s3_endpoint=_ENDPOINT)
    )

    assert provider._client.meta.endpoint_url == _ENDPOINT


def test_create_signs_presigned_urls_for_the_public_endpoint() -> None:
    provider = StorageProviderFactory.create(
        _settings(
            provider="minio",
            s3_endpoint="http://minio:9000",
            s3_public_endpoint=_ENDPOINT,
        )
    )

    assert provider._client.meta.endpoint_url == "http://minio:9000"
    assert provider._presign_client.meta.endpoint_url == _ENDPOINT


def test_create_raises_when_s3_bucket_missing() -> None:
    with pytest.raises(StorageConfigurationError, match="S3_BUCKET"):
        StorageProviderFactory.create(_settings(s3_bucket=None))


def test_create_raises_when_s3_region_missing() -> None:
    with pytest.raises(StorageConfigurationError, match="S3_REGION"):
        StorageProviderFactory.create(_settings(s3_region=None))


def test_create_raises_for_gcs_not_yet_supported() -> None:
    with pytest.raises(StorageConfigurationError, match="gcs"):
        StorageProviderFactory.create(_settings(provider="gcs"))


def test_create_raises_for_unknown_provider() -> None:
    with pytest.raises(StorageConfigurationError, match="Unknown"):
        StorageProviderFactory.create(_settings(provider="unknown"))
