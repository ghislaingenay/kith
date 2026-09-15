"""Request ID generation and correlation middleware (FR-2, TD-007 §3)."""

import uuid

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware:
    """Generates a UUID v4 `request_id` per request, binds it to structlog's
    contextvars so every log statement made within this request's async
    context includes it (FR-2's "Logged"), and returns it in the
    `X-Request-ID` response header (FR-2's "Header").
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = str(uuid.uuid4())
        bind_request_id(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                header_key = REQUEST_ID_HEADER.lower().encode()
                headers = [
                    (k, v)
                    for (k, v) in message.get("headers", [])
                    if k.lower() != header_key
                ]
                headers.append((header_key, request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            bind_request_id(None)


def get_request_id() -> str | None:
    """Read the current request's `request_id` out of structlog's
    contextvars (bound by `RequestIDMiddleware`), for callers that need to
    propagate it across a process boundary — e.g. into a worker job's args
    (FR-2's "Propagated: Passed to worker jobs").

    Returns `None` outside a request context (e.g. a cron job with no
    inbound request).
    """
    return structlog.contextvars.get_contextvars().get("request_id")


def bind_request_id(request_id: str | None) -> None:
    """Bind `request_id` into structlog's contextvars so it's merged onto
    every log line in this async context (FR-2), without passing it as an
    explicit param through every call. Used by `RequestIDMiddleware` per
    HTTP request, and again by worker jobs at job start — arq jobs run in a
    separate process, so each job re-binds from the value propagated via
    `get_request_id()`. Clears first so one job's id can't leak into the
    next job handled by the same long-lived worker process.
    """
    structlog.contextvars.clear_contextvars()
    if request_id is not None:
        structlog.contextvars.bind_contextvars(request_id=request_id)
