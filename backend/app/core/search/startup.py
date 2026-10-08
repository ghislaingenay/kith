"""Startup check that the search index and pipeline were created by the script."""

from core.search.exceptions import SearchIndexMissingError, SearchPipelineMissingError
from core.search.mapping import SEARCH_PIPELINE
from core.search.provider import SearchIndex


async def require_search_index(search_index: SearchIndex) -> None:
    if not await search_index.alias_exists():
        raise SearchIndexMissingError(search_index.alias)
    if not await search_index.search_pipeline_exists():
        raise SearchPipelineMissingError(SEARCH_PIPELINE)
