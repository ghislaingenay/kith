"""Unit tests for the Origin-header check. `container.cors_settings()` is
a module-level Singleton already resolved (with whatever `CORS_ALLOWED_ORIGINS`
was set, if any) by the time any test module imports `main` — so, like
tests/tenants/test_dependencies.py's `get_db_session` test, the container is
mocked rather than relied on."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from core.security import dependencies
from core.security.exceptions import OriginNotAllowedError


def _mock_container(allowed_origins: list[str]) -> MagicMock:
    mock_container = MagicMock()
    mock_container.cors_settings.return_value = SimpleNamespace(
        allowed_origins=allowed_origins
    )
    return mock_container


async def test_allows_a_request_with_no_origin_header() -> None:
    with patch.object(dependencies, "container", _mock_container([])):
        await dependencies.require_allowed_origin(origin=None)  # must not raise


async def test_allows_an_origin_on_the_allow_list() -> None:
    with patch.object(
        dependencies, "container", _mock_container(["http://localhost:3000"])
    ):
        await dependencies.require_allowed_origin(origin="http://localhost:3000")


async def test_rejects_an_origin_not_on_the_allow_list() -> None:
    with (
        patch.object(
            dependencies, "container", _mock_container(["http://localhost:3000"])
        ),
        pytest.raises(OriginNotAllowedError),
    ):
        await dependencies.require_allowed_origin(origin="http://evil.example.com")


async def test_rejects_any_origin_when_the_allow_list_is_empty() -> None:
    with (
        patch.object(dependencies, "container", _mock_container([])),
        pytest.raises(OriginNotAllowedError),
    ):
        await dependencies.require_allowed_origin(origin="http://localhost:3000")
