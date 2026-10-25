"""Unit tests for `UserRepository`/`ProfileRepository` against a fake
`AsyncSession` — no real database needed (see tests/support/fake_db.py).
"""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from structlog.testing import capture_logs

from tests.support.fake_db import FakeAsyncSession, FakeResult
from users.exceptions import UserNotFound
from users.models import Profile, User
from users.repository import ProfileRepository, UserRepository

_USER_ID = str(uuid.uuid4())


def _make_user() -> User:
    return User(
        id=_USER_ID,
        email="a@example.com",
    )


def _make_profile() -> Profile:
    return Profile(id=str(uuid.uuid4()), user_id=_USER_ID, first_name="Ada")


async def test_get_by_email_returns_user_when_found() -> None:
    user = _make_user()
    session = FakeAsyncSession(execute_results=[FakeResult(scalar=user)])
    repository = UserRepository(session)

    result = await repository.get_by_email("a@example.com")

    assert result is user


async def test_get_by_email_returns_none_when_absent() -> None:
    session = FakeAsyncSession(execute_results=[FakeResult(scalar=None)])
    repository = UserRepository(session)

    result = await repository.get_by_email("missing@example.com")

    assert result is None


async def test_get_by_user_id_returns_user_when_found() -> None:
    user = _make_user()
    session = FakeAsyncSession(execute_results=[FakeResult(scalar=user)])
    repository = UserRepository(session)

    result = await repository.get_by_user_id(_USER_ID)

    assert result is user


async def test_create_user_adds_commits_and_refreshes() -> None:
    user = _make_user()
    session = FakeAsyncSession()
    repository = UserRepository(session)

    result = await repository.create_user(user)

    assert result is user
    assert session.added == [user]
    assert session.commit_count == 1
    assert session.refreshed == [user]


async def test_get_or_create_user_returns_existing_user_without_creating() -> None:
    user = _make_user()
    session = FakeAsyncSession(execute_results=[FakeResult(scalar=user)])
    repository = UserRepository(session)

    user_result, is_created = await repository.get_or_create_user("a@example.com")

    assert user_result is user
    assert is_created is False
    assert session.added == []
    assert session.commit_count == 0


async def test_get_or_create_user_creates_when_absent() -> None:
    session = FakeAsyncSession(execute_results=[FakeResult(scalar=None)])
    repository = UserRepository(session)

    user_result, is_created = await repository.get_or_create_user("b@example.com")

    assert user_result.email == "b@example.com"
    assert is_created is True
    assert session.commit_count == 1
    assert session.refreshed == [user_result]
    assert session.rollback_count == 0


async def test_get_or_create_user_also_creates_the_profile() -> None:
    """Every User gets a Profile at signup (mvp-design.md: "First sign-in is
    signup; it creates the User and Profile") — a User must never exist
    without one."""
    session = FakeAsyncSession(execute_results=[FakeResult(scalar=None)])
    repository = UserRepository(session)

    user_result, _ = await repository.get_or_create_user("b@example.com")

    assert len(session.added) == 2
    added_user, added_profile = session.added
    assert added_user is user_result
    assert isinstance(added_profile, Profile)
    assert added_profile.user_id == user_result.id


async def test_get_or_create_user_recovers_from_concurrent_insert_race() -> None:
    # A second request creates the row first: our insert hits the unique
    # constraint, so we roll back and re-fetch what the other request wrote.
    existing_user = _make_user()
    session = FakeAsyncSession(
        execute_results=[FakeResult(scalar=None), FakeResult(scalar=existing_user)],
        commit_side_effects=[IntegrityError("INSERT", {}, Exception("dup key"))],
    )
    repository = UserRepository(session)

    user_result, is_created = await repository.get_or_create_user("a@example.com")

    assert user_result is existing_user
    assert is_created is False
    assert session.rollback_count == 1


async def test_get_or_create_user_raises_user_not_found_when_recovery_finds_nothing() -> (
    None
):
    session = FakeAsyncSession(
        execute_results=[FakeResult(scalar=None), FakeResult(scalar=None)],
        commit_side_effects=[IntegrityError("INSERT", {}, Exception("dup key"))],
    )
    repository = UserRepository(session)

    with pytest.raises(UserNotFound):
        await repository.get_or_create_user("a@example.com")


async def test_get_or_create_user_failure_is_logged_without_the_email() -> None:
    session = FakeAsyncSession(
        execute_results=[FakeResult(scalar=None), FakeResult(scalar=None)],
        commit_side_effects=[IntegrityError("INSERT", {}, Exception("dup key"))],
    )
    repository = UserRepository(session)

    with capture_logs() as logs, pytest.raises(UserNotFound):
        await repository.get_or_create_user("a@example.com")

    assert [log["event"] for log in logs] == ["user_get_or_create_failed"]
    assert "a@example.com" not in str(logs)


async def test_update_user_commits_and_refreshes_without_re_adding() -> None:
    user = _make_user()
    session = FakeAsyncSession()
    repository = UserRepository(session)

    result = await repository.update_user(user)

    assert result is user
    assert session.added == []
    assert session.commit_count == 1
    assert session.refreshed == [user]


async def test_profile_get_by_user_id_returns_profile_when_found() -> None:
    profile = _make_profile()
    session = FakeAsyncSession(execute_results=[FakeResult(scalar=profile)])
    repository = ProfileRepository(session)

    result = await repository.get_by_user_id(_USER_ID)

    assert result is profile


async def test_profile_get_by_user_id_returns_none_when_absent() -> None:
    session = FakeAsyncSession(execute_results=[FakeResult(scalar=None)])
    repository = ProfileRepository(session)

    result = await repository.get_by_user_id(_USER_ID)

    assert result is None


async def test_create_profile_adds_commits_and_refreshes() -> None:
    profile = _make_profile()
    session = FakeAsyncSession()
    repository = ProfileRepository(session)

    result = await repository.create_profile(profile)

    assert result is profile
    assert session.added == [profile]
    assert session.commit_count == 1
    assert session.refreshed == [profile]


async def test_update_profile_commits_and_refreshes_without_re_adding() -> None:
    profile = _make_profile()
    session = FakeAsyncSession()
    repository = ProfileRepository(session)

    result = await repository.update_profile(profile)

    assert result is profile
    assert session.added == []
    assert session.commit_count == 1
    assert session.refreshed == [profile]
