"""Unit tests for the documents domain's env-driven settings."""

import pytest

from documents.config import UploadSettings

_DEFAULT_MAX_FILE_BYTES = 20 * 1024 * 1024


def test_defaults_are_a_20_mb_cap_and_a_ten_minute_link() -> None:
    settings = UploadSettings()

    assert settings.max_file_bytes == _DEFAULT_MAX_FILE_BYTES
    assert settings.presigned_url_ttl_seconds == 600
    assert settings.max_pages == 100


def test_defaults_are_20_documents_100_mb_5_pending_and_30_starts_an_hour() -> None:
    settings = UploadSettings()

    assert settings.max_documents == 20
    assert settings.max_storage_bytes == 100 * 1024 * 1024
    assert settings.max_pending_per_user == 5
    assert settings.max_allowed_per_hour == 30
    assert settings.pending_expiry_seconds == 30 * 60


def test_every_value_is_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPLOAD_MAX_FILE_BYTES", "1000")
    monkeypatch.setenv("UPLOAD_PRESIGNED_URL_TTL_SECONDS", "90")
    monkeypatch.setenv("UPLOAD_MAX_PAGES", "7")
    monkeypatch.setenv("UPLOAD_MAX_DOCUMENTS", "3")
    monkeypatch.setenv("UPLOAD_MAX_STORAGE_BYTES", "4000")
    monkeypatch.setenv("UPLOAD_MAX_PENDING_PER_USER", "2")
    monkeypatch.setenv("UPLOAD_MAX_STARTS_PER_HOUR", "9")
    monkeypatch.setenv("UPLOAD_PENDING_EXPIRY_SECONDS", "120")

    settings = UploadSettings()

    assert settings.max_file_bytes == 1000
    assert settings.presigned_url_ttl_seconds == 90
    assert settings.max_pages == 7
    assert settings.max_documents == 3
    assert settings.max_storage_bytes == 4000
    assert settings.max_pending_per_user == 2
    assert settings.max_allowed_per_hour == 9
    assert settings.pending_expiry_seconds == 120
