"""The app's startup: each missing model key is a warning that reaches Sentry,
since it means every Ask or Search is affected. The lifespan runs for real,
with the container's infrastructure replaced by stand-ins."""

from collections.abc import Iterator

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from sentry_sdk.types import Event

import main
from core.container import container
from core.rerank.config import RerankSettings
from tests.support.fake_search_index import FakeSearchIndex
from tests.support.sentry_recorder import warning_messages


class _Closeable:
    """A database engine, Redis client or mailer that only needs closing."""

    async def close(self) -> None:
        pass

    async def dispose(self) -> None:
        pass


@pytest.fixture
def no_model_keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    async def schema_at_head(_engine: object) -> None:
        pass

    monkeypatch.setattr(main, "warn_if_schema_out_of_date", schema_at_head)
    with container.override_providers(
        db_engine=providers.Object(_Closeable()),
        cache_provider=providers.Object(_Closeable()),
        rate_limiter=providers.Object(_Closeable()),
        mailer=providers.Object(_Closeable()),
        job_queue=providers.Object(_Closeable()),
        search_index=providers.Object(FakeSearchIndex(index_exists=True)),
        query_embedding_provider=providers.Object(None),
        rerank_settings=providers.Object(RerankSettings(enabled=True)),
        reranker=providers.Object(None),
        answer_provider=providers.Object(None),
    ):
        yield


async def test_each_missing_model_key_is_reported_to_sentry_at_startup(
    no_model_keys: None, sentry_events: list[Event]
) -> None:
    async with main.lifespan(FastAPI()):
        pass

    assert warning_messages(sentry_events) == [
        "voyage_api_key_missing",
        "rerank_voyage_api_key_missing",
        "answer_provider_missing",
    ]
