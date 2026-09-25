"""HTTP tests for POST /uploads/{id}/finalize: what a caller gets back and
what storage, the database and the job queue hold afterwards."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.storage.dependencies import get_storage_provider
from core.storage.exceptions import StorageError
from documents.models import Document
from main import app
from tenants.permissions import Role
from tests.documents.conftest import Caller, make_pdf, make_tenant, sha256_hex
from tests.support.fake_job_queue import FakeJobQueue
from tests.support.fake_storage import FakeStorageProvider

_TWO_PAGE_PDF = make_pdf(pages=2)


async def _start_upload(
    client: AsyncClient, data: bytes, *, filename: str = "report.pdf"
) -> str:
    response = await client.post(
        "/api/v1/uploads/init",
        json={
            "filename": filename,
            "size": len(data),
            "content_type": "application/pdf",
            "sha256": sha256_hex(data),
        },
    )
    return response.json()["upload_id"]


def _send_from_browser(
    storage: FakeStorageProvider, caller: Caller, upload_id: str, data: bytes
) -> None:
    storage.put_object(f"pending/{caller.tenant_id}/{upload_id}", data)


async def _document_count(db_session: AsyncSession) -> int:
    return await db_session.scalar(select(func.count()).select_from(Document)) or 0


async def _finalize(client: AsyncClient, upload_id: str):
    return await client.post(f"/api/v1/uploads/{upload_id}/finalize")


async def test_a_valid_pdf_becomes_an_uploaded_document(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    response = await _finalize(client, upload_id)

    assert response.status_code == 200
    document = response.json()
    assert document["ingestion_status"] == "uploaded"
    assert document["size_bytes"] == len(_TWO_PAGE_PDF)
    assert document["page_count"] == 2
    assert document["content_hash"] == sha256_hex(_TWO_PAGE_PDF)


async def test_the_object_moves_from_the_temporary_key_to_its_permanent_key(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    temporary_key = f"pending/{caller.tenant_id}/{upload_id}"
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    document = (await _finalize(client, upload_id)).json()

    permanent_key = f"tenants/{caller.tenant_id}/documents/{document['id']}.pdf"
    assert storage.objects[permanent_key] == _TWO_PAGE_PDF
    assert temporary_key not in storage.keys


async def test_an_ingest_job_is_enqueued_with_only_the_ids(
    client: AsyncClient,
    storage: FakeStorageProvider,
    job_queue: FakeJobQueue,
    caller: Caller,
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    document = (await _finalize(client, upload_id)).json()

    [job] = job_queue.jobs
    assert job.queue == "ingest"
    assert job.job_id == document["id"]
    assert job.payload == {
        "document_id": document["id"],
        "tenant_id": str(caller.tenant_id),
    }


async def test_finalizing_twice_returns_the_same_document_and_reenqueues(
    client: AsyncClient,
    storage: FakeStorageProvider,
    job_queue: FakeJobQueue,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    first = (await _finalize(client, upload_id)).json()
    second_response = await _finalize(client, upload_id)

    assert second_response.status_code == 200
    assert second_response.json() == first
    assert await _document_count(db_session) == 1
    assert [job.job_id for job in job_queue.jobs] == [first["id"], first["id"]]


async def test_the_display_name_is_the_sanitised_filename(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    upload_id = await _start_upload(
        client, _TWO_PAGE_PDF, filename="C:\\docs\\..\\evil/Q3 budget.pdf"
    )
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    document = (await _finalize(client, upload_id)).json()

    assert document["name"] == "Q3 budget.pdf"


class _StorageThatCannotDelete(FakeStorageProvider):
    async def delete(self, key):
        raise StorageError("storage unavailable")


async def test_a_failed_cleanup_of_the_temporary_object_does_not_fail_finalize(
    client: AsyncClient, caller: Caller
) -> None:
    storage = _StorageThatCannotDelete()
    app.dependency_overrides[get_storage_provider] = lambda: storage
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    response = await _finalize(client, upload_id)

    assert response.status_code == 200


async def test_another_tenants_upload_cannot_be_finalized(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)
    caller.tenant_id = await make_tenant(db_session)

    response = await _finalize(client, upload_id)

    assert response.status_code == 404
    assert await _document_count(db_session) == 0


async def test_an_unknown_upload_is_not_found(client: AsyncClient) -> None:
    response = await _finalize(client, str(uuid.uuid4()))

    assert response.status_code == 404


async def test_a_viewer_cannot_finalize(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)
    caller.role = Role.VIEWER

    response = await _finalize(client, upload_id)

    assert response.status_code == 403


async def test_finalizing_before_the_file_arrived_is_a_conflict_and_can_be_retried(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)

    too_early = await _finalize(client, upload_id)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)
    retried = await _finalize(client, upload_id)

    assert too_early.status_code == 409
    assert retried.status_code == 200


async def test_a_file_of_a_different_size_than_announced_is_refused(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF + b"\n")

    response = await _finalize(client, upload_id)

    assert response.status_code == 422
    assert await _document_count(db_session) == 0


@pytest.mark.parametrize(
    "not_a_pdf", [b"just some text, not a pdf", b"%PDF-1.7 truncated"]
)
async def test_a_file_that_is_not_a_readable_pdf_is_refused(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
    not_a_pdf: bytes,
) -> None:
    upload_id = await _start_upload(client, not_a_pdf)
    _send_from_browser(storage, caller, upload_id, not_a_pdf)

    response = await _finalize(client, upload_id)

    assert response.status_code == 422
    assert await _document_count(db_session) == 0
    assert storage.copied == []
