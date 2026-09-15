"""Unit tests for tenants' FastAPI dependency wiring. See
tests/rbac/test_dependencies.py for why `get_db_session` is tested against a
mocked container rather than the real one.
"""

from unittest.mock import MagicMock, patch

from tenants import dependencies
from tenants.repository import TenantsRepository
from tests.support.fake_db import FakeAsyncSession


def test_get_tenant_repository_wraps_given_session() -> None:
    session = FakeAsyncSession()

    repository = dependencies.get_tenant_repository(session)

    assert isinstance(repository, TenantsRepository)
    assert repository.session is session


async def test_get_db_session_yields_session_from_container_factory() -> None:
    fake_session = FakeAsyncSession()

    def fake_session_factory():
        return fake_session

    mock_container = MagicMock()
    mock_container.db_session_factory.return_value = fake_session_factory

    with patch.object(dependencies, "container", mock_container):
        sessions = [session async for session in dependencies.get_db_session()]

    assert sessions == [fake_session]
