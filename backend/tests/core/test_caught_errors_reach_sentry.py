"""Errors the API catches and turns into a friendly 5xx are reported to
Sentry once each, and the response a User sees doesn't change. Each error is
raised from the `/me` route's first dependency, so the real app's exception
handlers turn it into the response."""

from collections.abc import Callable, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sentry_sdk.types import Event
from sqlalchemy.exc import OperationalError, TimeoutError

from auth.dependencies import get_current_user
from core.rerank.exceptions import RerankConfigurationError
from main import app
from tests.support.sentry_recorder import exception_types
from users.exceptions import ProfileNotFound


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def _raising(exc: Exception) -> Callable[[], None]:
    def dependency() -> None:
        raise exc

    return dependency


@pytest.mark.parametrize(
    ("exc", "status_code", "error"),
    [
        (
            OperationalError("SELECT 1", {}, ConnectionRefusedError("refused")),
            503,
            "db_unavailable",
        ),
        (TimeoutError("QueuePool limit reached"), 503, "db_timeout"),
        (
            RerankConfigurationError("rerank enabled without a model"),
            500,
            "internal_error",
        ),
        (
            ProfileNotFound("6f1c0a52-0000-0000-0000-000000000000"),
            500,
            "Profile not found",
        ),
    ],
    ids=[
        "db_operational_error",
        "db_timeout",
        "rerank_configuration",
        "missing_profile",
    ],
)
async def test_a_caught_error_keeps_its_response_and_is_reported_once(
    sentry_events: list[Event], exc: Exception, status_code: int, error: str
) -> None:
    app.dependency_overrides[get_current_user] = _raising(exc)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/me")

    assert response.status_code == status_code
    assert response.json()["error"] == error
    assert exception_types(sentry_events) == [type(exc).__name__]
