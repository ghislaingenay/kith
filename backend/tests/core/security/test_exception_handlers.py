from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.security.exception_handlers import register_security_exception_handlers
from core.security.exceptions import OriginNotAllowedError


def _make_app() -> FastAPI:
    app = FastAPI()
    register_security_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise OriginNotAllowedError("http://evil.example.com")

    return app


async def test_origin_not_allowed_maps_to_403_json() -> None:
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 403
    body = response.json()
    assert body["error"] == "origin_not_allowed"
    assert "http://evil.example.com" in body["message"]
