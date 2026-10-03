"""Startup check that the search index was created by the script."""

from core.search.exceptions import SearchIndexMissingError
from core.search.provider import SearchIndex


async def require_search_index(search_index: SearchIndex) -> None:
    if not await search_index.alias_exists():
        raise SearchIndexMissingError(search_index.alias)
