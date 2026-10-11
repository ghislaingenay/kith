"""Unit tests for the credits domain's env-driven settings."""

import pytest

from credits.config import CreditSettings


def test_defaults_are_a_200_credit_grant_and_a_20_credit_low_threshold() -> None:
    settings = CreditSettings()

    assert settings.starting_grant_credits == 200
    assert settings.low_threshold_credits == 20


def test_every_value_is_overridable_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STARTING_CREDIT_GRANT", "50")
    monkeypatch.setenv("CREDIT_LOW_THRESHOLD", "5")

    settings = CreditSettings()

    assert settings.starting_grant_credits == 50
    assert settings.low_threshold_credits == 5
