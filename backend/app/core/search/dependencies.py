"""FastAPI dependency wiring for the search core module."""

from core.container import container
from core.search.provider import SearchIndex


def get_search_index() -> SearchIndex:
    return container.search_index()
