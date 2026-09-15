import json

import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.logging.config import LoggingSettings, configure_logging
from core.logging.middleware import RequestIDMiddleware, bind_request_id, get_request_id


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/ping")
    def ping() -> dict[str, str | None]:
        return {"request_id": get_request_id()}

    return app


def test_response_includes_x_request_id_header() -> None:
    client = TestClient(_make_app())

    response = client.get("/ping")

    assert "X-Request-ID" in response.headers


def test_request_id_is_available_inside_the_handler() -> None:
    client = TestClient(_make_app())

    response = client.get("/ping")

    assert response.json()["request_id"] == response.headers["X-Request-ID"]


def test_each_request_gets_a_distinct_request_id() -> None:
    client = TestClient(_make_app())

    first = client.get("/ping").headers["X-Request-ID"]
    second = client.get("/ping").headers["X-Request-ID"]

    assert first != second


def test_get_request_id_returns_none_outside_a_request_context() -> None:
    structlog.contextvars.clear_contextvars()

    assert get_request_id() is None


def test_bind_request_id_makes_it_appear_on_log_lines(capsys) -> None:
    configure_logging(LoggingSettings(level="INFO", format="json"))
    logger = structlog.get_logger()

    bind_request_id("req-abc")
    logger.info("did a thing")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["request_id"] == "req-abc"


def test_bind_request_id_with_none_clears_prior_binding(capsys) -> None:
    configure_logging(LoggingSettings(level="INFO", format="json"))
    logger = structlog.get_logger()
    bind_request_id("stale-id")

    bind_request_id(None)
    logger.info("did a thing")

    payload = json.loads(capsys.readouterr().out.strip())
    assert "request_id" not in payload
