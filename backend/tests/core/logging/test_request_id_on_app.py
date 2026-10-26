"""The real app tags every response, log line and Sentry event of a request
with the same request ID (tests/core/logging/test_middleware.py covers the
middleware on its own)."""

import json
from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient, Response
from sentry_sdk.types import Event
from sqlalchemy.exc import OperationalError

from auth.dependencies import get_current_user
from core.logging.config import LoggingSettings, configure_logging
from main import app

_ME_URL = "/api/v1/me"
_HEALTH_URL = "/health"


@pytest.fixture(autouse=True)
def _clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def _database_down() -> None:
    raise OperationalError("SELECT 1", {}, ConnectionRefusedError("refused"))


async def _get(path: str) -> Response:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(path)


async def test_a_normal_response_carries_a_request_id() -> None:
    response = await _get(_HEALTH_URL)

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


async def test_a_4xx_response_carries_a_request_id() -> None:
    response = await _get("/api/v1/no-such-route")

    assert response.status_code == 404
    assert response.headers["X-Request-ID"]


async def test_a_5xx_from_an_exception_handler_carries_a_request_id() -> None:
    app.dependency_overrides[get_current_user] = _database_down

    response = await _get(_ME_URL)

    assert response.status_code == 503
    assert response.headers["X-Request-ID"]


async def test_two_requests_get_different_request_ids() -> None:
    first = await _get(_HEALTH_URL)
    second = await _get(_HEALTH_URL)

    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


async def test_a_log_line_written_during_a_request_carries_its_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(LoggingSettings(level="INFO", format="json"))
    app.dependency_overrides[get_current_user] = _database_down

    response = await _get(_ME_URL)

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    errors = [line for line in lines if line["level"] == "ERROR"]
    assert errors
    assert {line["request_id"] for line in errors} == {response.headers["X-Request-ID"]}


async def test_a_sentry_event_raised_during_a_request_carries_its_request_id(
    sentry_events: list[Event],
) -> None:
    app.dependency_overrides[get_current_user] = _database_down

    response = await _get(_ME_URL)

    assert len(sentry_events) == 1
    assert sentry_events[0]["tags"]["request_id"] == response.headers["X-Request-ID"]
