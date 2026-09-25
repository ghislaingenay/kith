"""Unit tests for the documents domain's env-driven settings."""

import pytest

from documents.config import UploadSettings


def test_defaults_are_a_20_mb_cap_and_a_ten_minute_link() -> None:
    settings = UploadSettings()

    assert settings.max_file_bytes == 20 * 1024 * 1024
    assert settings.presigned_url_ttl_seconds == 600


def test_both_values_are_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UPLOAD_MAX_FILE_BYTES", "1000")
    monkeypatch.setenv("UPLOAD_PRESIGNED_URL_TTL_SECONDS", "90")

    settings = UploadSettings()

    assert settings.max_file_bytes == 1000
    assert settings.presigned_url_ttl_seconds == 90
