"""HTTP tests for POST /uploads/{id}/finalize: what a caller gets back and
what storage, the database and the job queue hold afterwards."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_user
from auth.exceptions import AuthenticationError
from core.jobs.dependencies import get_job_queue
from core.storage.dependencies import get_storage_provider
from core.storage.exceptions import StorageError
from documents.models import Document, Upload
from main import app
from tenants.permissions import Role
from tests.documents.conftest import (
    INIT_URL,
    PDF_CONTENT_TYPE,
    Caller,
    finalize_upload,
    make_encrypted_pdf,
    make_pdf,
    make_tenant,
    sha256_hex,
)
from tests.support.fake_job_queue import FakeJobQueue
from tests.support.fake_storage import FakeStorageProvider

_TWO_PAGE_PDF = make_pdf(pages=2)
_DEFAULT_FILENAME = "report.pdf"
_THREE_PAGE_PDF = make_pdf(pages=3)


async def _start_upload(
    client: AsyncClient,
    data: bytes,
    *,
    filename: str = _DEFAULT_FILENAME,
    declared_sha256: str | None = None,
) -> str:
    response = await client.post(
        INIT_URL,
        json={
            "filename": filename,
            "size": len(data),
            "content_type": PDF_CONTENT_TYPE,
            "sha256": declared_sha256 or sha256_hex(data),
        },
    )
    return response.json()["upload_id"]


def _send_from_browser(
    storage: FakeStorageProvider, caller: Caller, upload_id: str, data: bytes
) -> None:
    storage.put_object(f"pending/{caller.tenant_id}/{upload_id}", data)


async def _document_count(db_session: AsyncSession) -> int:
    return await db_session.scalar(select(func.count()).select_from(Document)) or 0


async def _upload_outcome(
    db_session: AsyncSession, upload_id: str
) -> tuple[str, str | None]:
    row = (
        await db_session.execute(
            select(Upload.status, Upload.rejection_reason).where(
                Upload.id == uuid.UUID(upload_id)
            )
        )
    ).one()
    return row.status, row.rejection_reason


async def test_a_valid_pdf_becomes_an_uploaded_document(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    response = await finalize_upload(client, upload_id)

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

    document = (await finalize_upload(client, upload_id)).json()

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

    document = (await finalize_upload(client, upload_id)).json()

    [job] = job_queue.jobs
    assert job.queue == "ingest"
    assert job.job_id == document["id"]
    assert job.payload == {
        "document_id": document["id"],
        "tenant_id": str(caller.tenant_id),
    }


async def test_finalizing_twice_returns_the_same_document_and_one_ingest_job(
    client: AsyncClient,
    storage: FakeStorageProvider,
    job_queue: FakeJobQueue,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    first = (await finalize_upload(client, upload_id)).json()
    second_response = await finalize_upload(client, upload_id)

    assert second_response.status_code == 200
    assert second_response.json() == first
    assert await _document_count(db_session) == 1
    assert [job.job_id for job in job_queue.jobs] == [first["id"]]


class _QueueThatFailsOnce(FakeJobQueue):
    async def enqueue(self, queue, function, payload, *, job_id):
        if not getattr(self, "has_failed", False):
            self.has_failed = True
            raise ConnectionError("queue unavailable")
        await super().enqueue(queue, function, payload, job_id=job_id)


async def test_finalizing_again_after_a_failed_enqueue_still_queues_the_ingest_job(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    queue = _QueueThatFailsOnce()
    app.dependency_overrides[get_job_queue] = lambda: queue
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    with pytest.raises(ConnectionError):
        await finalize_upload(client, upload_id)
    retried = await finalize_upload(client, upload_id)

    assert retried.status_code == 200
    assert await _document_count(db_session) == 1
    assert [job.job_id for job in queue.jobs] == [retried.json()["id"]]


async def test_the_display_name_is_the_sanitised_filename(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    upload_id = await _start_upload(
        client, _TWO_PAGE_PDF, filename="C:\\docs\\..\\evil/Q3 budget.pdf"
    )
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    document = (await finalize_upload(client, upload_id)).json()

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

    response = await finalize_upload(client, upload_id)

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

    response = await finalize_upload(client, upload_id)

    assert response.status_code == 404
    assert await _document_count(db_session) == 0


class _StorageWhoseObjectChangesAfterTheSizeCheck(FakeStorageProvider):
    async def head(self, key):
        metadata = await super().head(key)
        self.put_object(key, _THREE_PAGE_PDF)
        return metadata


async def test_a_file_replaced_after_the_size_check_is_refused(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    storage = _StorageWhoseObjectChangesAfterTheSizeCheck()
    app.dependency_overrides[get_storage_provider] = lambda: storage
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)

    response = await finalize_upload(client, upload_id)

    assert response.status_code == 422
    assert await _document_count(db_session) == 0
    assert storage.copied == []


async def test_an_unauthenticated_caller_cannot_finalize(client: AsyncClient) -> None:
    def _not_signed_in() -> None:
        raise AuthenticationError("missing session")

    app.dependency_overrides[get_current_user] = _not_signed_in

    response = await finalize_upload(client, str(uuid.uuid4()))

    assert response.status_code == 401


async def test_an_unknown_upload_is_not_found(client: AsyncClient) -> None:
    response = await finalize_upload(client, str(uuid.uuid4()))

    assert response.status_code == 404


async def test_a_viewer_cannot_finalize(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)
    caller.role = Role.VIEWER

    response = await finalize_upload(client, upload_id)

    assert response.status_code == 403


async def test_finalizing_before_the_file_arrived_is_a_conflict_and_can_be_retried(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    upload_id = await _start_upload(client, _TWO_PAGE_PDF)

    too_early = await finalize_upload(client, upload_id)
    _send_from_browser(storage, caller, upload_id, _TWO_PAGE_PDF)
    retried = await finalize_upload(client, upload_id)

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

    response = await finalize_upload(client, upload_id)

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

    response = await finalize_upload(client, upload_id)

    assert response.status_code == 422
    assert "could not be read" in response.json()["message"]
    assert await _document_count(db_session) == 0
    assert storage.copied == []
    assert f"pending/{caller.tenant_id}/{upload_id}" not in storage.keys
    assert (await _upload_outcome(db_session, upload_id))[0] == "rejected"


async def test_a_body_that_does_not_match_the_declared_hash_is_refused_as_corrupt(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    damaged = _TWO_PAGE_PDF[:-1] + b"X"
    upload_id = await _start_upload(
        client, _TWO_PAGE_PDF, declared_sha256=sha256_hex(_TWO_PAGE_PDF)
    )
    _send_from_browser(storage, caller, upload_id, damaged)

    response = await finalize_upload(client, upload_id)

    assert response.status_code == 422
    assert "corrupt" in response.json()["message"].lower()
    assert await _document_count(db_session) == 0
    assert f"pending/{caller.tenant_id}/{upload_id}" not in storage.keys
    status, reason = await _upload_outcome(db_session, upload_id)
    assert status == "rejected"
    assert reason == response.json()["message"]


async def test_a_password_protected_pdf_is_refused_with_that_reason(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    encrypted = make_encrypted_pdf()
    upload_id = await _start_upload(client, encrypted)
    _send_from_browser(storage, caller, upload_id, encrypted)

    response = await finalize_upload(client, upload_id)

    assert response.status_code == 422
    assert "password-protected" in response.json()["message"]
    assert await _document_count(db_session) == 0
    assert f"pending/{caller.tenant_id}/{upload_id}" not in storage.keys
    assert (await _upload_outcome(db_session, upload_id))[0] == "rejected"


async def test_a_pdf_over_the_page_cap_is_refused_with_the_cap_in_the_message(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    too_long = make_pdf(pages=101)
    upload_id = await _start_upload(client, too_long)
    _send_from_browser(storage, caller, upload_id, too_long)

    response = await finalize_upload(client, upload_id)

    assert response.status_code == 422
    assert "100 pages" in response.json()["message"]
    assert await _document_count(db_session) == 0
    assert f"pending/{caller.tenant_id}/{upload_id}" not in storage.keys
    assert (await _upload_outcome(db_session, upload_id))[0] == "rejected"


async def test_a_pdf_of_exactly_the_page_cap_is_accepted(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    at_the_cap = make_pdf(pages=100)
    upload_id = await _start_upload(client, at_the_cap)
    _send_from_browser(storage, caller, upload_id, at_the_cap)

    response = await finalize_upload(client, upload_id)

    assert response.status_code == 200


async def test_finalizing_a_refused_upload_again_repeats_the_refusal(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    encrypted = make_encrypted_pdf()
    upload_id = await _start_upload(client, encrypted)
    _send_from_browser(storage, caller, upload_id, encrypted)
    first = await finalize_upload(client, upload_id)

    again = await finalize_upload(client, upload_id)

    assert again.status_code == 422
    assert again.json()["message"] == first.json()["message"]
    assert await _document_count(db_session) == 0
