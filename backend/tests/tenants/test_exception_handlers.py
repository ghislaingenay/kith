from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tenants.exception_handlers import register_tenant_exception_handlers
from tenants.exceptions import TenantAlreadyExistsError, TenantNotFound


def _make_app() -> FastAPI:
    app = FastAPI()
    register_tenant_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise TenantNotFound("tenant-123")

    return app


async def test_tenant_not_found_maps_to_404_json() -> None:
    transport = ASGITransport(app=_make_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "Tenant not found"
    assert "tenant-123" in body["message"]


def _make_app_tenant_already_exists() -> FastAPI:
    app = FastAPI()
    register_tenant_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise TenantAlreadyExistsError("test-tenant")

    return app


async def test_tenant_already_exists_maps_to_400_json() -> None:
    transport = ASGITransport(app=_make_app_tenant_already_exists())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "Tenant already exists"
    assert "test-tenant" in body["message"]
