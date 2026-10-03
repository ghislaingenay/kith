"""Errors raised by the search core module."""

ALREADY_EXISTS_ERROR = "resource_already_exists_exception"
"""The `error` type OpenSearch returns when creating an index that exists."""


class SearchError(Exception):
    """Base class for search-index errors."""


class SearchIndexMissingError(SearchError):
    """The search index alias does not exist yet."""

    def __init__(self, alias: str) -> None:
        super().__init__(
            f"Search index alias {alias!r} does not exist. "
            "Create it with `make search-index-create`."
        )
        self.alias = alias


class SearchUnavailableError(SearchError):
    """The search store could not be reached or refused the request. The only
    failure the retry handler retries and the circuit breaker counts."""

