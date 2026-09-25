"""Unit tests for the documents domain's env-driven settings."""

import pytest

from documents.config import UploadSettings

_DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024


def test_defaults_are_a_20_mb_cap_and_a_ten_minute_link() -> None:
    settings = UploadSettings()

    assert settings.max_file_bytes == _DEFAULT_MAX_FILE_BYTES
    assert settings.presigned_url_ttl_seconds == 600
    assert settings.max_pages == 100


def test_every_value_is_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPLOAD_MAX_FILE_BYTES", "1000")
    monkeypatch.setenv("UPLOAD_PRESIGNED_URL_TTL_SECONDS", "90")
    monkeypatch.setenv("UPLOAD_MAX_PAGES", "7")

    settings = UploadSettings()

    assert settings.max_file_bytes == 1000
    assert settings.presigned_url_ttl_seconds == 90
    assert settings.max_pages == 7
