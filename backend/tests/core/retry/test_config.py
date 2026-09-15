from core.retry.config import RetrySettings


def test_defaults_when_no_env_vars_set(monkeypatch) -> None:
    monkeypatch.delenv("RETRY_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("RETRY_BASE_DELAY", raising=False)
    monkeypatch.delenv("RETRY_MAX_DELAY", raising=False)
    monkeypatch.delenv("RETRY_JITTER", raising=False)

    settings = RetrySettings()

    assert settings.max_attempts == 3
    assert settings.base_delay == 0.5
    assert settings.max_delay == 10.0
    assert settings.jitter is True


def test_settings_overridden_by_env_vars(monkeypatch) -> None:
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("RETRY_BASE_DELAY", "1.5")
    monkeypatch.setenv("RETRY_MAX_DELAY", "30")
    monkeypatch.setenv("RETRY_JITTER", "false")

    settings = RetrySettings()

    assert settings.max_attempts == 5
    assert settings.base_delay == 1.5
    assert settings.max_delay == 30
    assert settings.jitter is False
