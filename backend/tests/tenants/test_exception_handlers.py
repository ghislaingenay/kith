from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from tenants.exception_handlers import register_tenant_exception_handlers
from tenants.exceptions import (
    PermissionDenied,
    TenantAlreadyExistsError,
    TenantNotFound,
    UnknownRoleOrActionError,
)


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


def _make_app_unknown_role_or_action() -> FastAPI:
    app = FastAPI()
    register_tenant_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise UnknownRoleOrActionError(role="superuser", action="search")

    return app


async def test_unknown_role_or_action_maps_to_500_json() -> None:
    transport = ASGITransport(app=_make_app_unknown_role_or_action())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"] == "Unknown role or action"
    assert "superuser" not in body["message"]


def _make_app_permission_denied() -> FastAPI:
    app = FastAPI()
    register_tenant_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise PermissionDenied("settings")

    return app


async def test_permission_denied_maps_to_403_json_distinct_from_401() -> None:
    transport = ASGITransport(app=_make_app_permission_denied())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 403
    assert response.status_code != 401
    body = response.json()
    assert body["error"] == "Permission denied"
    assert "settings" in body["message"]
