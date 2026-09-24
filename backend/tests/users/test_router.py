"""HTTP-level tests for the users domain router — dependency overrides only,
no DB (mirrors tests/tenants/test_router.py's ASGITransport pattern). The real
`ProfileService` runs; only the repository and storage are replaced."""

import uuid

import pytest
from auth.dependencies import get_current_user
from auth.exceptions import AuthenticationError
from auth.schemas import AuthenticatedUser
from core.storage.dependencies import get_storage_provider
from httpx import ASGITransport, AsyncClient
from main import app
from users.dependencies import get_profile_repository
from users.models import Profile

from tests.support.fake_storage import FakeStorageProvider

_USER = AuthenticatedUser(
    id=uuid.uuid4(),
    email="jane@example.com",
    email_verified=True,
    is_active=True,
)


class FakeProfileRepository:
    """In-memory stand-in holding at most one Profile, the caller's."""

    def __init__(self, profile: Profile | None = None) -> None:
        self.profile = profile

    async def get_by_user_id(self, user_id: str) -> Profile | None:
        return self.profile

    async def create_profile(self, profile: Profile) -> Profile:
        self.profile = profile
        return profile

    async def update_profile(self, profile: Profile) -> Profile:
        self.profile = profile
        return profile


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _override(
    repository: FakeProfileRepository,
    storage: FakeStorageProvider | None = None,
    user: AuthenticatedUser = _USER,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_profile_repository] = lambda: repository
    app.dependency_overrides[get_storage_provider] = lambda: (
        storage or FakeStorageProvider()
    )


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _signed_up_profile() -> Profile:
    """The empty Profile a User has right after signup (see
    UserRepository.get_or_create_user) — every fixture that saves through
    `ProfileService` starts from this, since a Profile always exists by the
    time Settings/Profile can be reached."""
    return Profile(user_id=_USER.id)


class TestUpdateMyProfile:
    async def test_sets_the_name_on_the_signup_created_profile(self) -> None:
        repository = FakeProfileRepository(_signed_up_profile())
        _override(repository)

        async with _client() as client:
            response = await client.patch(
                "/api/v1/users/me/profile", json={"name": "Jane Doe"}
            )

        assert response.status_code == 200
        assert response.json() == {
            "email": "jane@example.com",
            "name": "Jane Doe",
            "avatar_url": None,
        }
        assert repository.profile is not None
        assert repository.profile.first_name == "Jane Doe"

    async def test_changes_an_existing_name_and_keeps_the_avatar(self) -> None:
        key = f"user/{_USER.id}/avatar/avatar.png"
        profile = Profile(user_id=_USER.id, first_name="Jane", avatar_url=key)
        _override(FakeProfileRepository(profile))

        async with _client() as client:
            response = await client.patch(
                "/api/v1/users/me/profile", json={"name": "Janet"}
            )

        body = response.json()
        assert body["name"] == "Janet"
        assert (
            body["avatar_url"]
            == f"https://cdn.example.com/{key}?signature=fake&method=GET"
        )

    async def test_trims_the_name(self) -> None:
        _override(FakeProfileRepository(_signed_up_profile()))

        async with _client() as client:
            response = await client.patch(
                "/api/v1/users/me/profile", json={"name": "  Jane  "}
            )

        assert response.json()["name"] == "Jane"

    @pytest.mark.parametrize("blank", ["", "   ", None])
    async def test_blank_name_clears_it(self, blank: str | None) -> None:
        profile = Profile(user_id=_USER.id, first_name="Jane")
        _override(FakeProfileRepository(profile))

        async with _client() as client:
            response = await client.patch(
                "/api/v1/users/me/profile", json={"name": blank}
            )

        assert response.status_code == 200
        assert response.json()["name"] is None

    async def test_rejects_a_name_longer_than_100_characters(self) -> None:
        _override(FakeProfileRepository())

        async with _client() as client:
            response = await client.patch(
                "/api/v1/users/me/profile", json={"name": "a" * 101}
            )

        assert response.status_code == 422

    async def test_returns_401_when_unauthenticated(self) -> None:
        async def _raise_unauthenticated():
            raise AuthenticationError("unauthorized")

        _override(FakeProfileRepository())
        app.dependency_overrides[get_current_user] = _raise_unauthenticated

        async with _client() as client:
            response = await client.patch(
                "/api/v1/users/me/profile", json={"name": "Jane"}
            )

        assert response.status_code == 401

    async def test_returns_500_when_the_user_has_no_profile_row(self) -> None:
        """Defensive: every User gets a Profile at signup, so a missing row
        here is a data-integrity bug, not something a client caused."""
        _override(FakeProfileRepository())

        async with _client() as client:
            response = await client.patch(
                "/api/v1/users/me/profile", json={"name": "Jane"}
            )

        assert response.status_code == 500


_AVATAR_PNG_KEY = f"user/{_USER.id}/avatar/avatar.png"
_MAX_AVATAR_BYTES = 2 * 1024 * 1024


async def _put_avatar(
    client: AsyncClient, data: bytes, content_type: str, filename: str = "me.png"
):
    return await client.put(
        "/api/v1/users/me/avatar", files={"file": (filename, data, content_type)}
    )


class TestUploadMyAvatar:
    async def test_stores_png_privately_at_a_fixed_key_and_returns_a_presigned_url(
        self,
    ) -> None:
        storage = FakeStorageProvider()
        _override(FakeProfileRepository(_signed_up_profile()), storage)

        async with _client() as client:
            response = await _put_avatar(client, b"fake-png-bytes", "image/png")

        assert response.status_code == 200
        assert response.json()["avatar_url"] == (
            f"https://cdn.example.com/{_AVATAR_PNG_KEY}?signature=fake&method=GET"
        )
        assert storage.uploaded == [
            {"key": _AVATAR_PNG_KEY, "public": False, "content_type": "image/png"}
        ]

    async def test_records_the_stored_key_on_the_profile(self) -> None:
        """The row keeps the object key; only the response carries a URL."""
        repository = FakeProfileRepository(_signed_up_profile())
        _override(repository)

        async with _client() as client:
            await _put_avatar(client, b"fake-png-bytes", "image/png")

        assert repository.profile is not None
        assert repository.profile.avatar_url == _AVATAR_PNG_KEY

    async def test_keeps_the_existing_name(self) -> None:
        profile = Profile(user_id=_USER.id, first_name="Jane")
        _override(FakeProfileRepository(profile))

        async with _client() as client:
            response = await _put_avatar(client, b"fake-png-bytes", "image/png")

        assert response.json()["name"] == "Jane"

    async def test_reupload_as_jpeg_deletes_the_other_extension_variants(self) -> None:
        storage = FakeStorageProvider()
        _override(FakeProfileRepository(_signed_up_profile()), storage)

        async with _client() as client:
            await _put_avatar(client, b"fake-jpg-bytes", "image/jpeg", "me.jpg")

        assert storage.uploaded[0]["key"] == f"user/{_USER.id}/avatar/avatar.jpg"
        assert set(storage.deleted) == {
            f"user/{_USER.id}/avatar/avatar.png",
            f"user/{_USER.id}/avatar/avatar.jpeg",
        }

    async def test_rejects_an_unsupported_content_type(self) -> None:
        storage = FakeStorageProvider()
        _override(FakeProfileRepository(), storage)

        async with _client() as client:
            response = await _put_avatar(client, b"GIF89a", "image/gif", "me.gif")

        assert response.status_code == 422
        assert storage.uploaded == []

    async def test_rejects_an_empty_file(self) -> None:
        storage = FakeStorageProvider()
        _override(FakeProfileRepository(), storage)

        async with _client() as client:
            response = await _put_avatar(client, b"", "image/png")

        assert response.status_code == 422
        assert storage.uploaded == []

    async def test_rejects_a_file_larger_than_2mb(self) -> None:
        storage = FakeStorageProvider()
        _override(FakeProfileRepository(), storage)

        async with _client() as client:
            response = await _put_avatar(
                client, b"x" * (_MAX_AVATAR_BYTES + 1), "image/png"
            )

        assert response.status_code == 422
        assert storage.uploaded == []

    async def test_accepts_a_file_of_exactly_2mb(self) -> None:
        _override(FakeProfileRepository(_signed_up_profile()))

        async with _client() as client:
            response = await _put_avatar(client, b"x" * _MAX_AVATAR_BYTES, "image/png")

        assert response.status_code == 200

    async def test_returns_500_when_the_user_has_no_profile_row(self) -> None:
        """Defensive: every User gets a Profile at signup, so a missing row
        here is a data-integrity bug, not something a client caused."""
        _override(FakeProfileRepository())

        async with _client() as client:
            response = await _put_avatar(client, b"fake-png-bytes", "image/png")

        assert response.status_code == 500

    async def test_returns_401_when_unauthenticated(self) -> None:
        async def _raise_unauthenticated():
            raise AuthenticationError("unauthorized")

        storage = FakeStorageProvider()
        _override(FakeProfileRepository(_signed_up_profile()), storage)
        app.dependency_overrides[get_current_user] = _raise_unauthenticated

        async with _client() as client:
            response = await _put_avatar(client, b"fake-png-bytes", "image/png")

        assert response.status_code == 401
        assert storage.uploaded == []
