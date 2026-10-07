"""HTTP tests for the short-lived link the browser reads a Document's PDF
from, for the preview."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from documents.config import PreviewSettings
from documents.dependencies import get_preview_settings
from documents.models import Document, IngestionStatus
from main import app
from tenants.permissions import Role
from tests.documents.conftest import Caller, make_tenant
from tests.support.fake_storage import FakeStorageProvider

STORAGE_KEY = "tenants/acme/documents/report.pdf"


def _file_url(document_id: uuid.UUID) -> str:
    return f"/api/v1/documents/{document_id}/file-url"


async def _seed(
    db_session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    status: IngestionStatus = IngestionStatus.READY,
) -> Document:
    document = Document(
        tenant_id=tenant_id,
        uploader_id=None,
        name="report.pdf",
        size_bytes=1024,
        page_count=3,
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_key=STORAGE_KEY,
        ingestion_status=status,
        deleted_at=(
            datetime(2026, 9, 1, tzinfo=UTC)
            if status == IngestionStatus.DELETED
            else None
        ),
    )
    db_session.add(document)
    await db_session.commit()
    return document


async def test_returns_a_presigned_get_url_for_the_documents_file(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    document = await _seed(db_session, tenant_id=caller.tenant_id)

    response = await client.get(_file_url(document.id))

    assert response.status_code == 200
    assert response.json() == {
        "url": f"https://cdn.example.com/{STORAGE_KEY}?signature=fake&method=GET",
        "expires_in": 5 * 60,
    }


async def test_the_link_lives_as_long_as_the_settings_say(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
    storage: FakeStorageProvider,
) -> None:
    app.dependency_overrides[get_preview_settings] = lambda: PreviewSettings(
        preview_url_ttl_seconds=90
    )
    document = await _seed(db_session, tenant_id=caller.tenant_id)

    response = await client.get(_file_url(document.id))

    assert response.json()["expires_in"] == 90
    assert storage.presigned_gets == [{"key": STORAGE_KEY, "ttl": 90}]


@pytest.mark.parametrize("role", list(Role))
async def test_every_role_may_read_a_documents_file_link(
    client: AsyncClient, db_session: AsyncSession, caller: Caller, role: Role
) -> None:
    caller.role = role
    document = await _seed(db_session, tenant_id=caller.tenant_id)

    response = await client.get(_file_url(document.id))

    assert response.status_code == 200


async def test_a_deleted_document_has_no_file_link(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
    storage: FakeStorageProvider,
) -> None:
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, status=IngestionStatus.DELETED
    )

    response = await client.get(_file_url(document.id))

    assert response.status_code == 404
    assert storage.presigned_gets == []


async def test_another_tenants_document_has_no_file_link(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
    storage: FakeStorageProvider,
) -> None:
    theirs = await _seed(db_session, tenant_id=await make_tenant(db_session))

    response = await client.get(_file_url(theirs.id))

    assert response.status_code == 404
    assert storage.presigned_gets == []


async def test_a_document_that_does_not_exist_has_no_file_link(
    client: AsyncClient,
) -> None:
    response = await client.get(_file_url(uuid.uuid4()))

    assert response.status_code == 404

