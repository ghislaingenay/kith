"""Fixtures for the asks domain's HTTP tests: the documents domain's real
app, Postgres and OpenSearch (see tests/documents/conftest.py), with the
fake answer provider in place of the answer model."""

from collections.abc import AsyncIterator, Iterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.answer.dependencies import get_answer_provider
from credits.dependencies import get_db_session as get_credits_db_session
from main import app
from tests.documents.conftest import (  # noqa: F401 — fixtures used by these tests
    caller,
    client,
    fake_embedding_provider,
    fake_reranker,
    fake_search_index,
    job_queue,
    search_endpoint,
    search_index,
    storage,
)
from tests.support.fake_answer_provider import FakeAnswerProvider


@pytest.fixture
def fake_answer_provider() -> FakeAnswerProvider:
    return FakeAnswerProvider()


@pytest.fixture(autouse=True)
def _ask_endpoint(
    search_endpoint: None,  # noqa: F811
    db_session: AsyncSession,
    fake_answer_provider: FakeAnswerProvider,
) -> Iterator[None]:
    """Every test here retrieves from the real OpenSearch container, is
    answered by the fake provider, and can read the Credit Balance."""

    async def _db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_answer_provider] = lambda: fake_answer_provider
    app.dependency_overrides[get_credits_db_session] = _db_session
    yield
    app.dependency_overrides.pop(get_answer_provider, None)
    app.dependency_overrides.pop(get_credits_db_session, None)
