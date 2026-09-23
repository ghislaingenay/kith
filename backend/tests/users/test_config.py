"""Unit tests for the users domain's env-driven settings."""

import pytest
from users.config import AvatarSettings


def test_avatar_url_ttl_defaults_to_four_hours() -> None:
    settings = AvatarSettings()

    assert settings.presigned_url_ttl_seconds == 4 * 60 * 60


def test_avatar_url_ttl_is_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AVATAR_PRESIGNED_URL_TTL_SECONDS", "600")

    settings = AvatarSettings()

    assert settings.presigned_url_ttl_seconds == 600
