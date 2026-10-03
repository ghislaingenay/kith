import pytest
from core.search.exceptions import SearchIndexMissingError
from core.search.startup import require_search_index

from tests.support.fake_search_index import FakeSearchIndex


async def test_passes_when_the_index_alias_exists() -> None:
    await require_search_index(FakeSearchIndex(index_exists=True))


async def test_refuses_to_start_naming_the_script_when_the_alias_is_missing() -> None:
    with pytest.raises(SearchIndexMissingError, match="make search-index-create"):
        await require_search_index(FakeSearchIndex(index_exists=False))
