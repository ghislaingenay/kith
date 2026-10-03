"""`SearchIndex` backed by OpenSearch."""

from core.search.config import SearchSettings
from core.search.exceptions import ALREADY_EXISTS_ERROR
from core.search.mapping import INDEX_ALIAS, index_body, versioned_index_name
from core.search.provider import SearchIndex
from opensearchpy import AsyncOpenSearch
from opensearchpy.exceptions import RequestError


class OpenSearchIndex(SearchIndex):
    def __init__(self, settings: SearchSettings) -> None:
        self._client = AsyncOpenSearch(hosts=[settings.search_url])
        self._index_name = versioned_index_name(settings.embedding_model_id)

    @property
    def alias(self) -> str:
        return INDEX_ALIAS

    async def ensure_index(self) -> None:
        if await self.alias_exists():
            return
        try:
            await self._client.indices.create(index=self._index_name, body=index_body())
        except RequestError as error:
            # A concurrent run created it between the check and the create.
            if error.error != ALREADY_EXISTS_ERROR:
                raise

    async def alias_exists(self) -> bool:
        return await self._client.indices.exists_alias(name=INDEX_ALIAS)

    async def close(self) -> None:
        await self._client.close()
