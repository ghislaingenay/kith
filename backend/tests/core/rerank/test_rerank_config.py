import pytest
from core.rerank.config import RerankSettings
from core.rerank.exceptions import RerankConfigurationError
from pydantic import ValidationError

_RERANK_VARIABLES = (
    "RERANK_ENABLED",
    "RERANK_MODEL",
    "RERANK_FETCH_SIZE",
    "RERANK_RESULT_LIMIT",
)


@pytest.fixture(autouse=True)
def _no_rerank_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in _RERANK_VARIABLES:
        monkeypatch.delenv(variable, raising=False)


def test_the_documented_defaults() -> None:
    settings = RerankSettings()

    assert settings.enabled is True
    assert settings.model == "rerank-3"
    assert settings.fetch_size == 50
    assert settings.result_limit == 5


def test_every_setting_can_be_overridden_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANK_ENABLED", "false")
    monkeypatch.setenv("RERANK_MODEL", "rerank-2.5")
    monkeypatch.setenv("RERANK_FETCH_SIZE", "40")
    monkeypatch.setenv("RERANK_RESULT_LIMIT", "8")

    settings = RerankSettings()

    assert settings.enabled is False
    assert settings.model == "rerank-2.5"
    assert settings.fetch_size == 40
    assert settings.result_limit == 8


def test_a_fetch_size_below_the_result_limit_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RERANK_FETCH_SIZE", "4")
    monkeypatch.setenv("RERANK_RESULT_LIMIT", "5")

    with pytest.raises(RerankConfigurationError, match="fetch size"):
        RerankSettings()


@pytest.mark.parametrize("variable", ["RERANK_FETCH_SIZE", "RERANK_RESULT_LIMIT"])
def test_sizes_must_be_positive(monkeypatch: pytest.MonkeyPatch, variable: str) -> None:
    monkeypatch.setenv(variable, "0")

    with pytest.raises(ValidationError):
        RerankSettings()
