"""FastAPI dependency wiring for the rerank core module."""

from core.container import container
from core.rerank.config import RerankSettings
from core.rerank.provider import Reranker


def get_rerank_settings() -> RerankSettings:
    return container.rerank_settings()


def get_reranker() -> Reranker | None:
    """`None` when there is no Voyage API key; built even when Rerank is
    switched off, since Ask's Retrieval decides whether to use it."""
    return container.reranker()
