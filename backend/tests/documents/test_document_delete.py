"""HTTP tests for deleting a Document: who may, what a soft delete changes,
and the purge job it queues."""

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from documents.config import UploadSettings
from documents.dependencies import get_upload_settings
from documents.models import Document, IngestionStatus
from main import app
from tenants.permissions import Role
from tests.documents.conftest import (
    Caller,
    init_upload,
    make_pdf,
    make_tenant,
    make_user,
    sha256_hex,
)
from tests.support.fake_job_queue import EnqueuedJob, FakeJobQueue

LIST_URL = "/api/v1/documents"


def _document_url(document_id: uuid.UUID) -> str:
    return f"{LIST_URL}/{document_id}"


async def _seed(
    db_session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    uploader_id: uuid.UUID | None,
    name: str = "report.pdf",
    status: IngestionStatus = IngestionStatus.READY,
    content_hash: str | None = None,
    deleted_at: datetime | None = None,
) -> Document:
    document = Document(
        tenant_id=tenant_id,
        uploader_id=uploader_id,
        name=name,
        size_bytes=1024,
        page_count=3,
        content_hash=content_hash or uuid.uuid4().hex + uuid.uuid4().hex,
        storage_key="tenants/x/documents/y.pdf",
        ingestion_status=status,
        deleted_at=deleted_at,
    )
    db_session.add(document)
    await db_session.commit()
    return document


async def test_the_uploader_can_delete_their_own_document(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=caller.user_id
    )

    response = await client.delete(_document_url(document.id))

    assert response.status_code == 204
    assert (await client.get(LIST_URL)).json() == []


async def test_deleting_records_who_deleted_it_and_when(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    caller.role = Role.ADMIN
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=await make_user(db_session)
    )
    await db_session.refresh(document)
    assert document.deleted_at is None
    assert document.deleted_by is None

    await client.delete(_document_url(document.id))

    await db_session.refresh(document)
    assert document.ingestion_status == IngestionStatus.DELETED
    assert document.deleted_by == caller.user_id
    assert document.deleted_at is not None


async def test_a_refused_delete_records_nothing(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=await make_user(db_session)
    )

    await client.delete(_document_url(document.id))

    await db_session.refresh(document)
    assert document.deleted_at is None
    assert document.deleted_by is None


async def test_deleting_twice_keeps_the_first_deletion_record(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=caller.user_id
    )
    await client.delete(_document_url(document.id))
    await db_session.refresh(document)
    first_deleted_at = document.deleted_at

    response = await client.delete(_document_url(document.id))

    assert response.status_code == 404
    await db_session.refresh(document)
    assert document.deleted_at == first_deleted_at


async def test_the_database_refuses_a_deleted_status_without_a_deletion_time(
    db_session: AsyncSession, caller: Caller
) -> None:
    with pytest.raises(IntegrityError):
        await _seed(
            db_session,
            tenant_id=caller.tenant_id,
            uploader_id=caller.user_id,
            status=IngestionStatus.DELETED,
            deleted_at=None,
        )


async def test_the_database_refuses_a_deletion_time_on_a_live_document(
    db_session: AsyncSession, caller: Caller
) -> None:
    with pytest.raises(IntegrityError):
        await _seed(
            db_session,
            tenant_id=caller.tenant_id,
            uploader_id=caller.user_id,
            status=IngestionStatus.READY,
            deleted_at=datetime.now(UTC),
        )


async def test_removing_the_deleting_user_empties_deleted_by(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=caller.user_id
    )
    await client.delete(_document_url(document.id))

    await db_session.execute(
        text("DELETE FROM users WHERE id = :id"), {"id": caller.user_id}
    )
    await db_session.commit()

    await db_session.refresh(document)
    assert document.deleted_by is None
    assert document.deleted_at is not None


async def test_deleting_queues_a_purge_job_on_the_tasks_queue(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
    job_queue: FakeJobQueue,
) -> None:
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=caller.user_id
    )

    await client.delete(_document_url(document.id))

    assert job_queue.jobs == [
        EnqueuedJob(
            queue="tasks",
            function="purge_document",
            payload={
                "document_id": str(document.id),
                "tenant_id": str(caller.tenant_id),
            },
            job_id=f"purge:{document.id}",
        )
    ]


@pytest.mark.parametrize("role", [Role.ADMIN, Role.OWNER])
async def test_an_admin_or_owner_can_delete_someone_elses_document(
    client: AsyncClient, db_session: AsyncSession, caller: Caller, role: Role
) -> None:
    caller.role = role
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=await make_user(db_session)
    )

    response = await client.delete(_document_url(document.id))

    assert response.status_code == 204
    assert (await client.get(LIST_URL)).json() == []


async def test_a_member_cannot_delete_someone_elses_document(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
    job_queue: FakeJobQueue,
) -> None:
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=await make_user(db_session)
    )

    response = await client.delete(_document_url(document.id))

    assert response.status_code == 403
    assert len((await client.get(LIST_URL)).json()) == 1
    assert job_queue.jobs == []


async def test_a_viewer_cannot_delete_a_document(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
    job_queue: FakeJobQueue,
) -> None:
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=caller.user_id
    )
    caller.role = Role.VIEWER

    response = await client.delete(_document_url(document.id))

    assert response.status_code == 403
    assert len((await client.get(LIST_URL)).json()) == 1
    assert job_queue.jobs == []


async def test_deleting_an_already_deleted_document_is_refused_without_a_second_purge(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
    job_queue: FakeJobQueue,
) -> None:
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=caller.user_id
    )
    await client.delete(_document_url(document.id))
    job_queue.jobs.clear()

    response = await client.delete(_document_url(document.id))

    assert response.status_code == 404
    assert job_queue.jobs == []


async def test_deleting_another_tenants_document_is_refused_without_side_effects(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
    job_queue: FakeJobQueue,
) -> None:
    caller.role = Role.OWNER
    other_tenant_id = await make_tenant(db_session)
    theirs = await _seed(
        db_session, tenant_id=other_tenant_id, uploader_id=await make_user(db_session)
    )

    response = await client.delete(_document_url(theirs.id))

    assert response.status_code == 404
    assert job_queue.jobs == []
    await db_session.refresh(theirs)
    assert theirs.ingestion_status == IngestionStatus.READY
    assert theirs.deleted_at is None
    assert theirs.deleted_by is None


async def test_deleting_a_document_that_does_not_exist_is_refused(
    client: AsyncClient,
) -> None:
    response = await client.delete(_document_url(uuid.uuid4()))

    assert response.status_code == 404


async def test_a_deleted_document_does_not_block_uploading_the_same_content_again(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    data = make_pdf()
    document = await _seed(
        db_session,
        tenant_id=caller.tenant_id,
        uploader_id=caller.user_id,
        content_hash=sha256_hex(data),
    )
    assert (await init_upload(client, data)).status_code == 409

    await client.delete(_document_url(document.id))

    assert (await init_upload(client, data)).status_code == 201


async def test_a_deleted_document_no_longer_counts_toward_the_documents_limit(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    app.dependency_overrides[get_upload_settings] = lambda: UploadSettings(
        UPLOAD_MAX_DOCUMENTS=1
    )
    document = await _seed(
        db_session, tenant_id=caller.tenant_id, uploader_id=caller.user_id
    )
    assert (await init_upload(client, make_pdf())).status_code == 409

    await client.delete(_document_url(document.id))

    assert (await init_upload(client, make_pdf())).status_code == 201
