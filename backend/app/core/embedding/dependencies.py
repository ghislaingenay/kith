"""FastAPI dependency wiring for the embedding core module."""

from core.container import container
from core.embedding.provider import EmbeddingProvider


def get_query_embedding_provider() -> EmbeddingProvider | None:
    return container.query_embedding_provider()
