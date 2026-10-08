"""FastAPI dependency wiring for the search core module."""

from core.container import container
from core.embedding.provider import EmbeddingProvider
from core.search.provider import SearchIndex


def get_search_index() -> SearchIndex:
    return container.search_index()


def get_query_embedding_provider() -> EmbeddingProvider | None:
    """`None` without a Voyage API key; Search then runs keyword only."""
    return container.query_embedding_provider()
