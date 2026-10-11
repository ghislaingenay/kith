import pytest
from core.answer.config import AnswerSettings
from core.answer.factory import create_answer_provider
from pydantic import ValidationError

_ANSWER_VARIABLES = (
    "ANSWER_PROVIDER",
    "ANSWER_MODEL",
    "ANSWER_REASONING_EFFORT",
    "ANSWER_MAX_OUTPUT_TOKENS",
)


@pytest.fixture(autouse=True)
def _no_answer_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in _ANSWER_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def test_the_documented_defaults() -> None:
    settings = AnswerSettings()

    assert settings.provider == "openai"
    assert settings.model == "gpt-6-luna"
    assert settings.reasoning_effort == "low"
    assert settings.max_output_tokens == 8_000


def test_every_setting_can_be_overridden_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANSWER_MODEL", "gpt-6.1-sol")
    monkeypatch.setenv("ANSWER_REASONING_EFFORT", "medium")
    monkeypatch.setenv("ANSWER_MAX_OUTPUT_TOKENS", "4000")

    settings = AnswerSettings()

    assert settings.model == "gpt-6.1-sol"
    assert settings.reasoning_effort == "medium"
    assert settings.max_output_tokens == 4_000


def test_an_unknown_provider_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANSWER_PROVIDER", "nobody")

    with pytest.raises(ValidationError):
        AnswerSettings()


def test_no_provider_until_the_openai_adapter_exists() -> None:
    assert create_answer_provider(AnswerSettings()) is None
