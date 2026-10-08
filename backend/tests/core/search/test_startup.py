import pytest
from core.search.exceptions import SearchIndexMissingError, SearchPipelineMissingError
from core.search.startup import require_search_index

from tests.support.fake_search_index import FakeSearchIndex


async def test_passes_when_the_index_alias_and_pipeline_exist() -> None:
    await require_search_index(FakeSearchIndex(index_exists=True))


async def test_refuses_to_start_naming_the_script_when_the_alias_is_missing() -> None:
    with pytest.raises(SearchIndexMissingError, match="make search-index-create"):
        await require_search_index(FakeSearchIndex(index_exists=False))


async def test_refuses_to_start_naming_the_script_when_the_pipeline_is_missing() -> (
    None
):
    index = FakeSearchIndex(index_exists=True)
    index.pipeline_exists = False

    with pytest.raises(SearchPipelineMissingError, match="make search-index-create"):
        await require_search_index(index)
