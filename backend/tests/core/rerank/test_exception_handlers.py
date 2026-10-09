from core.exceptions import register_exception_handlers
from core.rerank.config import RerankSettings
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _make_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        RerankSettings(fetch_size=4, result_limit=5)

    return app


async def test_contradictory_rerank_settings_answer_500_without_details() -> None:
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_error",
        "message": "The server is misconfigured",
    }
