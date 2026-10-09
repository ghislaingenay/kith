import pytest
from core.circuit_breaker.breaker import CircuitBreaker
from core.rerank.circuit_breaker_reranker import CircuitBreakerReranker
from core.rerank.config import RerankSettings
from core.rerank.factory import create_reranker


def _breaker() -> CircuitBreaker:
    return CircuitBreaker(
        name="rerank",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(),
    )


def test_a_reranker_even_when_rerank_is_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Ask's Retrieval decides, and `make retrieve` can force Rerank on.
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    reranker = create_reranker(RerankSettings(enabled=False), _breaker())

    assert isinstance(reranker, CircuitBreakerReranker)


def test_no_reranker_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # docker-compose passes an empty string when the variable is unset.
    monkeypatch.setenv("VOYAGE_API_KEY", "")

    assert create_reranker(RerankSettings(enabled=True), _breaker()) is None


def test_a_reranker_behind_the_breaker_when_switched_on_with_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    reranker = create_reranker(RerankSettings(enabled=True), _breaker())

    assert isinstance(reranker, CircuitBreakerReranker)
