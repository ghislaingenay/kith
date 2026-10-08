"""The ingest worker builds the embedding provider at startup, so a missing
Voyage API key must stop it with a message that names the variable (#66)."""

import pytest
from core.circuit_breaker.breaker import CircuitBreaker
from core.embedding.circuit_breaker_provider import CircuitBreakerEmbeddingProvider
from core.embedding.config import EmbeddingSettings
from core.embedding.factory import EmbeddingProviderFactory
from pydantic import ValidationError


def test_a_missing_api_key_is_refused_with_the_variable_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    with pytest.raises(ValidationError, match="VOYAGE_API_KEY"):
        EmbeddingSettings()


def test_an_empty_api_key_is_refused_with_the_variable_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # docker-compose passes an empty string when the variable is unset.
    monkeypatch.setenv("VOYAGE_API_KEY", "")

    with pytest.raises(ValidationError, match="VOYAGE_API_KEY"):
        EmbeddingSettings()


def test_the_factory_builds_a_provider_behind_the_breaker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    breaker = CircuitBreaker(
        name="embedding",
        failure_threshold=5,
        reset_timeout_seconds=30,
        failure_types=(),
    )

    provider = EmbeddingProviderFactory.create(EmbeddingSettings(), breaker)

    assert isinstance(provider, CircuitBreakerEmbeddingProvider)
