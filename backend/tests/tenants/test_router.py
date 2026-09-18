"""HTTP-level tests for the tenants domain router — dependency overrides
only, no DB (mirrors tests/test_main.py's ASGITransport pattern)."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from auth.dependencies import get_current_tenant, get_current_user
from auth.exceptions import AuthenticationError
from auth.schemas import AuthenticatedUser, TenantContext
from core.storage.dependencies import get_storage_provider
from core.storage.exceptions import StorageObjectNotFoundError
from core.storage.provider import StorageObjectMetadata
from main import app
from tenants.dependencies import get_tenants_service
from tenants.permissions import Role
from tenants.router import (
    tenants_logo_upload_rate_limit,
    tenants_read_rate_limit,
)
from tenants.schemas import TenantMembershipSummary

_USER = AuthenticatedUser(
    id=uuid.uuid4(),
    email="jane@example.com",
    email_verified=True,
    is_active=True,
)
_TENANT = TenantContext(tenant_id=uuid.uuid4(), role=Role.OWNER)


class FakeTenantsService:
    def __init__(self) -> None:
        self.memberships: list[TenantMembershipSummary] = []
        self.create_calls: list[dict] = []
        self.next_created: TenantMembershipSummary | None = None

    async def list_my_memberships(self, user_id):
        return self.memberships

    async def create_tenant(self, *, user_id, name):
        self.create_calls.append({"user_id": user_id, "name": name})
        return self.next_created or TenantMembershipSummary(
            tenant_id=uuid.uuid4(),
            tenant_name=name,
            tenant_slug=name.lower(),
            role=Role.OWNER,
        )


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def _override(service: FakeTenantsService, user: AuthenticatedUser = _USER) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_tenants_service] = lambda: service


class TestListMyTenants:
    async def test_returns_memberships_with_no_x_tenant_id_header(self) -> None:
        """The whole point of this endpoint: it works without already
        knowing a tenant id — proves the /me chicken-and-egg fix."""
        service = FakeTenantsService()
        service.memberships = [
            TenantMembershipSummary(
                tenant_id=uuid.uuid4(),
                tenant_name="Acme",
                tenant_slug="acme",
                role=Role.OWNER,
            )
        ]
        _override(service)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/tenants")

        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["tenant_name"] == "Acme"

    async def test_returns_empty_list_when_no_memberships(self) -> None:
        service = FakeTenantsService()
        _override(service)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/tenants")

        assert response.status_code == 200
        assert response.json() == []

    async def test_returns_401_when_unauthenticated(self) -> None:
        async def _raise_unauthenticated():
            raise AuthenticationError("unauthorized")

        app.dependency_overrides[get_current_user] = _raise_unauthenticated
        app.dependency_overrides[get_tenants_service] = lambda: FakeTenantsService()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/tenants")

        assert response.status_code == 401


class TestCreateTenant:
    async def test_creates_tenant_and_returns_201(self) -> None:
        service = FakeTenantsService()
        service.next_created = TenantMembershipSummary(
            tenant_id=uuid.uuid4(),
            tenant_name="Acme",
            tenant_slug="acme",
            role=Role.OWNER,
        )
        _override(service)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/tenants", json={"name": "Acme"})

        assert response.status_code == 201
        body = response.json()
        assert body["tenant_name"] == "Acme"
        assert body["role"] == "owner"
        assert service.create_calls == [{"user_id": _USER.id, "name": "Acme"}]

    async def test_returns_422_when_name_missing(self) -> None:
        service = FakeTenantsService()
        _override(service)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/tenants", json={})

        assert response.status_code == 422

    async def test_returns_422_when_name_empty(self) -> None:
        service = FakeTenantsService()
        _override(service)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/tenants", json={"name": ""})

        assert response.status_code == 422

    async def test_returns_401_when_unauthenticated(self) -> None:
        async def _raise_unauthenticated():
            raise AuthenticationError("unauthorized")

        app.dependency_overrides[get_current_user] = _raise_unauthenticated
        app.dependency_overrides[get_tenants_service] = lambda: FakeTenantsService()

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/api/v1/tenants", json={"name": "Acme"})

        assert response.status_code == 401


class FakeStorageProvider:
    """In-memory stand-in — records uploads/deletes, serves `head` from a
    presedeed key set."""

    def __init__(self, existing_keys: set[str] | None = None) -> None:
        self.uploaded: list[dict] = []
        self.deleted: list[str] = []
        self.existing: set[str] = set(existing_keys or set())

    async def upload(self, key, stream, metadata=None, *, public=False):
        self.uploaded.append({"key": key, "public": public})
        self.existing.add(key)
        return f"https://cdn.example.com/{key}"

    async def delete(self, key):
        self.deleted.append(key)
        self.existing.discard(key)

    async def head(self, key):
        if key not in self.existing:
            raise StorageObjectNotFoundError(key)
        return StorageObjectMetadata(
            size=1, etag="e", last_modified="2026-01-01T00:00:00+00:00"
        )

    def public_url(self, key):
        return f"https://cdn.example.com/{key}"


def _override_logo(
    storage: FakeStorageProvider,
    *,
    user: AuthenticatedUser = _USER,
    tenant: TenantContext = _TENANT,
) -> None:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_tenant] = lambda: tenant
    app.dependency_overrides[get_storage_provider] = lambda: storage
    app.dependency_overrides[tenants_logo_upload_rate_limit] = lambda: None
    app.dependency_overrides[tenants_read_rate_limit] = lambda: None


_HEADERS = {"X-Tenant-ID": str(_TENANT.tenant_id)}


class TestUploadTenantLogo:
    @pytest.mark.parametrize("role", [Role.OWNER, Role.ADMIN])
    async def test_returns_201_for_owner_and_admin(self, role: Role) -> None:
        storage = FakeStorageProvider()
        tenant = TenantContext(tenant_id=_TENANT.tenant_id, role=role)
        _override_logo(storage, tenant=tenant)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/tenants/logo",
                files={"file": ("brand.png", b"fake-png-bytes", "image/png")},
                headers=_HEADERS,
            )

        assert response.status_code == 201

    @pytest.mark.parametrize("role", [Role.MEMBER, Role.VIEWER])
    async def test_returns_403_for_member_and_viewer(self, role: Role) -> None:
        storage = FakeStorageProvider()
        tenant = TenantContext(tenant_id=_TENANT.tenant_id, role=role)
        _override_logo(storage, tenant=tenant)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/tenants/logo",
                files={"file": ("brand.png", b"fake-png-bytes", "image/png")},
                headers=_HEADERS,
            )

        assert response.status_code == 403
        body = response.json()
        assert body["error"] == "Permission denied"
        assert "settings" in body["message"]
        assert storage.uploaded == []

    async def test_returns_401_when_unauthenticated(self) -> None:
        """403 from PermissionDenied must be distinguishable from the 401
        raised for an unauthenticated caller."""
        storage = FakeStorageProvider()
        _override_logo(storage)

        async def _raise_unauthenticated():
            raise AuthenticationError("unauthorized")

        app.dependency_overrides[get_current_tenant] = _raise_unauthenticated

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/tenants/logo",
                files={"file": ("brand.png", b"fake-png-bytes", "image/png")},
                headers=_HEADERS,
            )

        assert response.status_code == 401

    async def test_stores_png_at_fixed_key_and_returns_public_url(self) -> None:
        storage = FakeStorageProvider()
        _override_logo(storage)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/tenants/logo",
                files={"file": ("brand.png", b"fake-png-bytes", "image/png")},
                headers=_HEADERS,
            )

        assert response.status_code == 201
        expected_key = f"tenant/{_TENANT.tenant_id}/logo/logo.png"
        assert response.json() == {"url": f"https://cdn.example.com/{expected_key}"}
        assert storage.uploaded == [{"key": expected_key, "public": True}]

    async def test_deletes_other_extension_variants(self) -> None:
        storage = FakeStorageProvider()
        _override_logo(storage)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post(
                "/api/v1/tenants/logo",
                files={"file": ("brand.jpg", b"fake-jpg-bytes", "image/jpeg")},
                headers=_HEADERS,
            )

        assert storage.uploaded[0]["key"] == f"tenant/{_TENANT.tenant_id}/logo/logo.jpg"
        assert set(storage.deleted) == {
            f"tenant/{_TENANT.tenant_id}/logo/logo.png",
            f"tenant/{_TENANT.tenant_id}/logo/logo.jpeg",
        }

    async def test_rejects_unsupported_content_type(self) -> None:
        storage = FakeStorageProvider()
        _override_logo(storage)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/tenants/logo",
                files={"file": ("brand.gif", b"GIF89a", "image/gif")},
                headers=_HEADERS,
            )

        assert response.status_code == 422
        assert storage.uploaded == []

    async def test_rejects_empty_file(self) -> None:
        storage = FakeStorageProvider()
        _override_logo(storage)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/tenants/logo",
                files={"file": ("brand.png", b"", "image/png")},
                headers=_HEADERS,
            )

        assert response.status_code == 422
        assert storage.uploaded == []

    async def test_rejects_file_larger_than_2mb(self) -> None:
        storage = FakeStorageProvider()
        _override_logo(storage)
        oversized = b"x" * (2 * 1024 * 1024 + 1)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/tenants/logo",
                files={"file": ("brand.png", oversized, "image/png")},
                headers=_HEADERS,
            )

        assert response.status_code == 422
        assert storage.uploaded == []


class TestGetTenantLogo:
    async def test_returns_url_when_a_logo_exists(self) -> None:
        key = f"tenant/{_TENANT.tenant_id}/logo/logo.png"
        storage = FakeStorageProvider(existing_keys={key})
        _override_logo(storage)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/tenants/logo", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json() == {"url": f"https://cdn.example.com/{key}"}

    async def test_returns_null_when_no_logo_exists(self) -> None:
        storage = FakeStorageProvider()
        _override_logo(storage)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/tenants/logo", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json() == {"url": None}

    async def test_succeeds_for_viewer(self) -> None:
        """The logo read route is not gated beyond the tenant context —
        every Role, including the least-privileged Viewer, can fetch it."""
        key = f"tenant/{_TENANT.tenant_id}/logo/logo.png"
        storage = FakeStorageProvider(existing_keys={key})
        tenant = TenantContext(tenant_id=_TENANT.tenant_id, role=Role.VIEWER)
        _override_logo(storage, tenant=tenant)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/v1/tenants/logo", headers=_HEADERS)

        assert response.status_code == 200
        assert response.json() == {"url": f"https://cdn.example.com/{key}"}
