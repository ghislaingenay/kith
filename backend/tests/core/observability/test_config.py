import pytest
import sentry_sdk
from pydantic import ValidationError
from sentry_sdk.integrations.arq import ArqIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from core.observability.config import (
    SentrySettings,
    configure_sentry,
    scrub_event,
    traces_sampler,
)

_DSN = "https://public@o0.ingest.sentry.io/0"
_RELEASE = "649470b"
_PRODUCTION = "production"


def _asgi_sampling_context(path: str) -> dict:
    return {"asgi_scope": {"type": "http", "path": path}, "parent_sampled": None}


@pytest.fixture
def sentry_init_calls(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    calls: list[dict] = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kwargs: calls.append(kwargs))
    return calls


def test_defaults_when_no_env_vars_set(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SENTRY_DSN",
        "SENTRY_ENVIRONMENT",
        "SENTRY_RELEASE",
        "SENTRY_TRACES_SAMPLE_RATE",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = SentrySettings()

    assert settings.dsn == ""
    assert settings.environment == "local"
    assert settings.release is None
    assert settings.traces_sample_rate == 0.1


def test_settings_read_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTRY_DSN", _DSN)
    monkeypatch.setenv("SENTRY_ENVIRONMENT", _PRODUCTION)
    monkeypatch.setenv("SENTRY_RELEASE", _RELEASE)
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.5")

    settings = SentrySettings()

    assert settings.dsn == _DSN
    assert settings.environment == _PRODUCTION
    assert settings.release == _RELEASE
    assert settings.traces_sample_rate == 0.5


def test_empty_release_from_an_image_built_without_a_sha_is_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTRY_RELEASE", "")

    assert SentrySettings().release is None


@pytest.mark.parametrize("rate", [-0.1, 1.1])
def test_traces_sample_rate_outside_zero_to_one_is_refused(rate: float) -> None:
    with pytest.raises(ValidationError):
        SentrySettings(traces_sample_rate=rate)


def test_empty_dsn_leaves_sentry_off(sentry_init_calls: list[dict]) -> None:
    configure_sentry(SentrySettings(dsn="", environment=_PRODUCTION))

    assert sentry_init_calls == []


def test_local_environment_leaves_sentry_off_even_with_a_dsn(
    sentry_init_calls: list[dict],
) -> None:
    configure_sentry(SentrySettings(dsn=_DSN, environment="local"))

    assert sentry_init_calls == []


def test_dsn_starts_sentry_with_release_environment_and_both_integrations(
    sentry_init_calls: list[dict],
) -> None:
    configure_sentry(
        SentrySettings(dsn=_DSN, environment=_PRODUCTION, release=_RELEASE)
    )

    [options] = sentry_init_calls
    assert options["dsn"] == _DSN
    assert options["release"] == _RELEASE
    assert options["environment"] == _PRODUCTION
    integration_types = {type(i) for i in options["integrations"]}
    assert {FastApiIntegration, ArqIntegration} <= integration_types


def test_sentry_is_started_without_tenant_data_or_log_forwarding(
    sentry_init_calls: list[dict],
) -> None:
    configure_sentry(SentrySettings(dsn=_DSN, environment=_PRODUCTION))

    [options] = sentry_init_calls
    assert options["send_default_pii"] is False
    assert options["include_local_variables"] is False
    assert options["max_request_body_size"] == "never"
    assert options["enable_logs"] is False
    assert options["before_send"] is scrub_event
    assert options["before_send_transaction"] is scrub_event
    [logging_integration] = [
        i for i in options["integrations"] if isinstance(i, LoggingIntegration)
    ]
    assert logging_integration._handler is None
    assert logging_integration._breadcrumb_handler is None
    assert logging_integration._sentry_logs_handler is None


def test_sampler_never_samples_health(sentry_init_calls: list[dict]) -> None:
    configure_sentry(
        SentrySettings(dsn=_DSN, environment=_PRODUCTION, traces_sample_rate=1.0)
    )
    [options] = sentry_init_calls

    assert options["traces_sampler"](_asgi_sampling_context("/health")) == 0


def test_sampler_samples_other_requests_at_the_configured_rate() -> None:
    sampler = traces_sampler(0.25)

    assert sampler(_asgi_sampling_context("/api/v1/search")) == 0.25


def test_sampler_samples_worker_jobs_at_the_configured_rate() -> None:
    sampler = traces_sampler(0.25)

    assert sampler({"parent_sampled": None}) == 0.25


def test_scrubber_removes_bodies_cookies_auth_headers_and_emails() -> None:
    event = {
        "request": {
            "url": "https://app.example.com/api/v1/auth/magic-link",
            "method": "POST",
            "data": {"email": "owner@example.com"},
            "cookies": {"session": "secret-session"},
            "headers": {
                "Authorization": "Bearer secret-token",
                "Cookie": "session=secret-session",
                "X-Tenant-ID": "4f0c",
                "Content-Type": "application/json",
            },
        },
        "user": {"id": "u-1", "email": "owner@example.com"},
        "exception": {
            "values": [
                {"type": "ValueError", "value": "no account for owner@example.com"}
            ]
        },
    }

    scrubbed = scrub_event(event, {})

    assert scrubbed is not None
    request = scrubbed["request"]
    assert "data" not in request
    assert "cookies" not in request
    assert request["headers"] == {
        "X-Tenant-ID": "4f0c",
        "Content-Type": "application/json",
    }
    assert "email" not in scrubbed["user"]
    assert "owner@example.com" not in str(scrubbed)
