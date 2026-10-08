import pytest
from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.circuit_breaker_provider import CircuitBreakerEmbeddingProvider
from documents.query_embedding import create_query_embedding_provider


def _breaker() -> CircuitBreaker:
    return CircuitBreaker(
        name="embedding",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(),
    )


def test_no_provider_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "")

    assert create_query_embedding_provider(_breaker()) is None


def test_a_provider_behind_the_breaker_with_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    provider = create_query_embedding_provider(_breaker())

    assert isinstance(provider, CircuitBreakerEmbeddingProvider)
