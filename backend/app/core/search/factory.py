"""Factory for instantiating a `SearchIndex` from configuration."""

from core.search.config import SearchSettings
from core.search.opensearch_index import OpenSearchIndex
from core.search.provider import SearchIndex


class SearchIndexFactory:
    @staticmethod
    def create(settings: SearchSettings) -> SearchIndex:
        return OpenSearchIndex(settings)
