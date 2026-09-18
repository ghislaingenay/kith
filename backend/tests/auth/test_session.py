"""Unit tests for `SessionService` (ADR-0006)."""

import uuid

from auth.config import SESSION_TTL_SECONDS
from auth.session import SessionService
from tests.support.fake_cache import FakeCacheProvider


def _service() -> tuple[SessionService, FakeCacheProvider]:
    cache = FakeCacheProvider()
    return SessionService(cache), cache


class TestCreateSession:
    async def test_returns_an_opaque_id_whose_hash_is_the_only_thing_cached(
        self,
    ) -> None:
        service, cache = _service()

        raw_session_id = await service.create_session(uuid.uuid4())

        assert raw_session_id
        # The raw id is never itself a valid cache key — only its hash is.
        assert await cache.get(raw_session_id) is None

    async def test_two_sessions_for_the_same_user_get_different_raw_ids(self) -> None:
        service, _ = _service()
        user_id = uuid.uuid4()

        first = await service.create_session(user_id)
        second = await service.create_session(user_id)

        assert first != second


class TestResolveUserId:
    async def test_returns_the_user_id_for_a_valid_session(self) -> None:
        service, _ = _service()
        user_id = uuid.uuid4()
        raw_session_id = await service.create_session(user_id)

        result = await service.resolve_user_id(raw_session_id)

        assert result == user_id

    async def test_returns_none_for_an_unknown_session(self) -> None:
        service, _ = _service()

        result = await service.resolve_user_id("this-session-was-never-issued")

        assert result is None

    async def test_slides_the_ttl_forward_on_a_successful_lookup(self) -> None:
        service, cache = _service()
        user_id = uuid.uuid4()
        raw_session_id = await service.create_session(user_id)
        calls: list[tuple[str, int]] = []
        original_expire = cache.expire

        async def _tracking_expire(key: str, ttl_seconds: int) -> None:
            calls.append((key, ttl_seconds))
            await original_expire(key, ttl_seconds)

        cache.expire = _tracking_expire  # type: ignore[method-assign]

        await service.resolve_user_id(raw_session_id)

        assert len(calls) == 1
        assert calls[0][1] == SESSION_TTL_SECONDS

    async def test_does_not_slide_the_ttl_for_an_unknown_session(self) -> None:
        service, cache = _service()
        calls: list[tuple[str, int]] = []
        cache.expire = lambda key, ttl_seconds: calls.append((key, ttl_seconds))  # type: ignore[method-assign,func-returns-value]

        await service.resolve_user_id("does-not-exist")

        assert calls == []


class TestDeleteSession:
    async def test_a_deleted_session_no_longer_resolves(self) -> None:
        service, _ = _service()
        user_id = uuid.uuid4()
        raw_session_id = await service.create_session(user_id)

        await service.delete_session(raw_session_id)

        assert await service.resolve_user_id(raw_session_id) is None

    async def test_is_a_no_op_for_an_unknown_session(self) -> None:
        service, _ = _service()

        await service.delete_session("does-not-exist")  # must not raise

    async def test_does_not_delete_a_session_rotated_since_it_was_read(self) -> None:
        """Guards the value-guarded delete: if `raw_session_id`'s entry was
        overwritten by a fresh login between the read and the delete, the
        new session must survive."""
        service, cache = _service()
        user_id = uuid.uuid4()
        raw_session_id = await service.create_session(user_id)

        original_get = cache.get

        async def _get_then_rotate(key: str) -> str | None:
            value = await original_get(key)
            # Simulate a concurrent fresh login overwriting this same key
            # (same raw id would never recur, but the key can if a new
            # session happened to hash there — modeled directly for the test).
            await cache.set(key, str(uuid.uuid4()), ttl_seconds=SESSION_TTL_SECONDS)
            return value

        cache.get = _get_then_rotate  # type: ignore[method-assign]

        await service.delete_session(raw_session_id)

        cache.get = original_get  # type: ignore[method-assign]
        assert await service.resolve_user_id(raw_session_id) is not None
