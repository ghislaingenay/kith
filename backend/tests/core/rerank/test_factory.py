import pytest
from core.rerank.config import RerankSettings
from core.rerank.factory import create_reranker
from core.rerank.voyage_reranker import VoyageReranker


def test_no_reranker_when_rerank_is_switched_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    assert create_reranker(RerankSettings(enabled=False)) is None


def test_no_reranker_without_an_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    # docker-compose passes an empty string when the variable is unset.
    monkeypatch.setenv("VOYAGE_API_KEY", "")

    assert create_reranker(RerankSettings(enabled=True)) is None


def test_a_voyage_reranker_when_switched_on_with_a_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    assert isinstance(create_reranker(RerankSettings(enabled=True)), VoyageReranker)
