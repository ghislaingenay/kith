"""HTTP tests for duplicate refusal: identical content is stored once per
Tenant, whatever the filename, at start and again at finalize."""

import asyncio
import uuid
from collections.abc import AsyncIterator

from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import create_session_factory
from documents.dependencies import get_db_session
from documents.models import Document, IngestionStatus, Upload
from main import app
from tests.documents.conftest import Caller, make_pdf, make_tenant, sha256_hex
from tests.support.fake_storage import FakeStorageProvider
from users.models import Profile

_INIT_URL = "/api/v1/uploads/init"
_PDF_CONTENT_TYPE = "application/pdf"
_PDF = make_pdf(pages=2)


async def _init(client: AsyncClient, data: bytes, filename: str):
    return await client.post(
        _INIT_URL,
        json={
            "filename": filename,
            "size": len(data),
            "content_type": _PDF_CONTENT_TYPE,
            "sha256": sha256_hex(data),
        },
    )


def _send_from_browser(
    storage: FakeStorageProvider, caller: Caller, upload_id: str, data: bytes
) -> None:
    storage.put_object(f"pending/{caller.tenant_id}/{upload_id}", data)


async def _finalize(client: AsyncClient, upload_id: str):
    return await client.post(f"/api/v1/uploads/{upload_id}/finalize")


async def _upload_document(
    client: AsyncClient,
    storage: FakeStorageProvider,
    caller: Caller,
    filename: str,
    data: bytes = _PDF,
) -> dict:
    upload_id = (await _init(client, data, filename)).json()["upload_id"]
    _send_from_browser(storage, caller, upload_id, data)
    return (await _finalize(client, upload_id)).json()


async def _count(db_session: AsyncSession, model: type) -> int:
    return await db_session.scalar(select(func.count()).select_from(model)) or 0


async def test_identical_content_under_another_filename_is_refused_at_start(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    db_session.add(Profile(user_id=caller.user_id, first_name="Jane", last_name="Doe"))
    await db_session.commit()
    await _upload_document(client, storage, caller, "budget.pdf")
    uploads_before = await _count(db_session, Upload)

    response = await _init(client, _PDF, "budget copy (1).pdf")

    assert response.status_code == 409
    message = response.json()["message"]
    assert "budget.pdf" in message
    assert "Jane Doe" in message
    assert len(storage.presigned_puts) == 1, "no bytes were requested the second time"
    assert await _count(db_session, Upload) == uploads_before


async def test_a_soft_deleted_document_does_not_block_reuploading_its_content(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    first = await _upload_document(client, storage, caller, "budget.pdf")
    await db_session.execute(
        update(Document)
        .where(Document.id == uuid.UUID(first["id"]))
        .values(ingestion_status=IngestionStatus.DELETED)
    )
    await db_session.commit()

    second = await _upload_document(client, storage, caller, "budget again.pdf")

    assert second["id"] != first["id"]
    assert second["ingestion_status"] == "uploaded"


async def test_the_same_content_in_another_tenant_is_not_a_duplicate(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    await _upload_document(client, storage, caller, "budget.pdf")
    caller.tenant_id = await make_tenant(db_session)

    response = await _init(client, _PDF, "budget.pdf")

    assert response.status_code == 201


async def test_a_duplicate_names_the_uploader_by_email_when_they_have_no_profile(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    await _upload_document(client, storage, caller, "budget.pdf")

    response = await _init(client, _PDF, "budget again.pdf")

    assert response.status_code == 409
    assert "@example.com" in response.json()["message"]


async def test_two_concurrent_finalizes_of_identical_content_make_one_document(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    # Each request needs its own session: one AsyncSession can't run two
    # transactions at once.
    session_factory = create_session_factory(db_session.bind)

    async def _session_per_request() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    first_id = (await _init(client, _PDF, "one.pdf")).json()["upload_id"]
    second_id = (await _init(client, _PDF, "two.pdf")).json()["upload_id"]
    _send_from_browser(storage, caller, first_id, _PDF)
    _send_from_browser(storage, caller, second_id, _PDF)
    app.dependency_overrides[get_db_session] = _session_per_request

    responses = await asyncio.gather(
        _finalize(client, first_id), _finalize(client, second_id)
    )

    assert sorted(response.status_code for response in responses) == [200, 409]
    assert await _count(db_session, Document) == 1
    refused = next(r for r in responses if r.status_code == 409)
    assert "was already uploaded by" in refused.json()["message"]
    permanent_objects = [key for key in storage.keys if key.startswith("tenants/")]
    assert len(permanent_objects) == 1, "the loser's promoted copy is removed"
    assert not any(key.startswith("pending/") for key in storage.keys)
    outcomes = await db_session.scalars(select(Upload.status))
    assert sorted(outcomes) == ["completed", "rejected"]
