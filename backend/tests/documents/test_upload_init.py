"""HTTP tests for POST /uploads/init: what a caller is told, and which
presigned PUT storage is asked to sign."""

import base64
import hashlib

import pytest
from httpx import AsyncClient

from auth.dependencies import get_current_user
from auth.exceptions import AuthenticationError
from documents.config import UploadSettings
from documents.dependencies import get_upload_settings
from main import app
from tenants.permissions import Role
from tests.documents.conftest import Caller, sha256_hex
from tests.support.fake_storage import FakeStorageProvider

_PDF_BYTES = b"%PDF-1.4 not a real file, only its digest matters here"
_FILENAME = "Q3 secret budget.pdf"


def _init_body(**overrides) -> dict:
    return {
        "filename": _FILENAME,
        "size": len(_PDF_BYTES),
        "content_type": "application/pdf",
        "sha256": sha256_hex(_PDF_BYTES),
        **overrides,
    }


async def test_init_returns_a_presigned_put_to_a_temporary_key(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    response = await client.post("/api/v1/uploads/init", json=_init_body())

    assert response.status_code == 201
    body = response.json()
    assert body["method"] == "PUT"
    assert body["expires_in"] == 600
    assert f"pending/{caller.tenant_id}/{body['upload_id']}" in body["url"], (
        "the temporary key is keyed by Tenant id and Upload id"
    )
    assert body["headers"]["Content-Type"] == "application/pdf"


async def test_init_signs_the_exact_length_type_and_checksum(
    client: AsyncClient, storage: FakeStorageProvider
) -> None:
    await client.post("/api/v1/uploads/init", json=_init_body())

    [signed] = storage.presigned_puts
    assert signed["content_type"] == "application/pdf"
    assert signed["content_length"] == len(_PDF_BYTES)
    assert signed["ttl"] == 600
    expected_checksum = base64.b64encode(hashlib.sha256(_PDF_BYTES).digest()).decode()
    assert signed["checksum_sha256"] == expected_checksum


async def test_init_tells_the_browser_to_send_the_signed_checksum_header(
    client: AsyncClient,
) -> None:
    response = await client.post("/api/v1/uploads/init", json=_init_body())

    expected_checksum = base64.b64encode(hashlib.sha256(_PDF_BYTES).digest()).decode()
    assert response.json()["headers"]["x-amz-checksum-sha256"] == expected_checksum


async def test_the_temporary_key_never_contains_the_clients_filename(
    client: AsyncClient, storage: FakeStorageProvider
) -> None:
    response = await client.post("/api/v1/uploads/init", json=_init_body())

    [signed] = storage.presigned_puts
    for part in ("secret", "budget", "Q3", ".pdf"):
        assert part not in signed["key"]
        assert part not in response.json()["url"]


@pytest.mark.parametrize("role", [Role.OWNER, Role.ADMIN, Role.MEMBER])
async def test_roles_that_may_upload_can_start_an_upload(
    client: AsyncClient, caller: Caller, role: Role
) -> None:
    caller.role = role

    response = await client.post("/api/v1/uploads/init", json=_init_body())

    assert response.status_code == 201


async def test_a_viewer_cannot_start_an_upload(
    client: AsyncClient, caller: Caller, storage: FakeStorageProvider
) -> None:
    caller.role = Role.VIEWER

    response = await client.post("/api/v1/uploads/init", json=_init_body())

    assert response.status_code == 403
    assert storage.presigned_puts == []


async def test_an_unauthenticated_caller_gets_401(client: AsyncClient) -> None:
    def _not_signed_in() -> None:
        raise AuthenticationError("missing session")

    app.dependency_overrides[get_current_user] = _not_signed_in

    response = await client.post("/api/v1/uploads/init", json=_init_body())

    assert response.status_code == 401


async def test_a_declared_size_over_the_cap_is_refused(
    client: AsyncClient, storage: FakeStorageProvider
) -> None:
    over_the_cap = 20 * 1024 * 1024 + 1

    response = await client.post(
        "/api/v1/uploads/init", json=_init_body(size=over_the_cap)
    )

    assert response.status_code == 422
    assert "20 MB" in response.json()["message"]
    assert storage.presigned_puts == []


async def test_a_declared_size_at_the_cap_is_accepted(client: AsyncClient) -> None:
    at_the_cap = 20 * 1024 * 1024

    response = await client.post(
        "/api/v1/uploads/init", json=_init_body(size=at_the_cap)
    )

    assert response.status_code == 201


@pytest.mark.parametrize("content_type", ["image/png", "text/plain", ""])
async def test_a_non_pdf_content_type_is_refused(
    client: AsyncClient, storage: FakeStorageProvider, content_type: str
) -> None:
    response = await client.post(
        "/api/v1/uploads/init", json=_init_body(content_type=content_type)
    )

    assert response.status_code == 422
    assert "PDF" in response.json()["message"]
    assert storage.presigned_puts == []


async def test_the_size_cap_and_link_lifetime_come_from_the_settings(
    client: AsyncClient, storage: FakeStorageProvider
) -> None:
    app.dependency_overrides[get_upload_settings] = lambda: UploadSettings(
        UPLOAD_MAX_FILE_BYTES=100, UPLOAD_PRESIGNED_URL_TTL_SECONDS=30
    )

    too_big = await client.post("/api/v1/uploads/init", json=_init_body(size=101))
    fits = await client.post("/api/v1/uploads/init", json=_init_body(size=100))

    assert too_big.status_code == 422
    assert fits.status_code == 201
    assert fits.json()["expires_in"] == 30
    assert storage.presigned_puts[0]["ttl"] == 30
