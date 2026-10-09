"""FastAPI dependency wiring for the rerank core module."""

from core.container import container
from core.rerank.config import RerankSettings
from core.rerank.provider import Reranker


def get_rerank_settings() -> RerankSettings:
    return container.rerank_settings()


def get_reranker() -> Reranker | None:
    """`None` when Rerank is switched off or there is no Voyage API key."""
    return container.reranker()
