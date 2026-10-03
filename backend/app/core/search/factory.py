"""Factory for instantiating a `SearchIndex` from configuration."""

from core.circuit_breaker.breaker import CircuitBreaker
from core.search.circuit_breaker_index import CircuitBreakerSearchIndex
from core.search.config import SearchSettings
from core.search.opensearch_index import OpenSearchIndex
from core.search.provider import SearchIndex


class SearchIndexFactory:
    @staticmethod
    def create(settings: SearchSettings, breaker: CircuitBreaker) -> SearchIndex:
        return CircuitBreakerSearchIndex(OpenSearchIndex(settings), breaker)
