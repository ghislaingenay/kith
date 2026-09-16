"""Unit tests for users' FastAPI dependency wiring. `get_db_session` goes
through the module-level `container`, so it's tested against a mocked
stand-in rather than the real one (which would require a live DATABASE_URL).
"""

from unittest.mock import MagicMock, patch

from tests.support.fake_db import FakeAsyncSession
from users import dependencies
from users.repository import ProfileRepository, UserRepository


def test_get_user_repository_wraps_given_session() -> None:
    session = FakeAsyncSession()

    repository = dependencies.get_user_repository(session)

    assert isinstance(repository, UserRepository)
    assert repository.session is session


def test_get_profile_repository_wraps_given_session() -> None:
    session = FakeAsyncSession()

    repository = dependencies.get_profile_repository(session)

    assert isinstance(repository, ProfileRepository)
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
