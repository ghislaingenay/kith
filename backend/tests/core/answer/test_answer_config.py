import pytest
from core.answer.circuit_breaker_answer_provider import CircuitBreakerAnswerProvider
from core.answer.config import AnswerSettings
from core.answer.factory import create_answer_provider
from core.circuit_breaker.breaker import CircuitBreaker
from pydantic import ValidationError

_ANSWER_VARIABLES = (
    "ANSWER_PROVIDER",
    "ANSWER_MODEL",
    "ANSWER_REASONING_EFFORT",
    "ANSWER_MAX_OUTPUT_TOKENS",
    "OPENAI_API_KEY",
)


def _breaker() -> CircuitBreaker:
    return CircuitBreaker(
        name="answer",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(),
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


def test_the_openai_provider_when_an_openai_key_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    provider = create_answer_provider(AnswerSettings(), _breaker())

    # Behind the time limit and the `answer` breaker, as the reranker is.
    assert isinstance(provider, CircuitBreakerAnswerProvider)


@pytest.mark.parametrize("api_key", [None, ""])
def test_no_provider_without_an_openai_key(
    monkeypatch: pytest.MonkeyPatch, api_key: str | None
) -> None:
    # docker-compose passes an empty string when the variable is unset.
    if api_key is not None:
        monkeypatch.setenv("OPENAI_API_KEY", api_key)

    assert create_answer_provider(AnswerSettings(), _breaker()) is None
