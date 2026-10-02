"""HTTP tests for the Uploads Library's Documents list: what the caller's
Tenant holds, newest first, with each Document's Ingestion progress."""

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from documents.models import Document, IngestionStage, IngestionStatus
from tenants.permissions import Role
from tests.documents.conftest import Caller, make_tenant, make_user
from users.models import Profile

LIST_URL = "/api/v1/documents"
SUMMARY_URL = "/api/v1/documents/summary"
_NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
_DELETED_AT = _NOW


async def _seed(
    db_session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    uploader_id: uuid.UUID | None,
    name: str,
    age: timedelta = timedelta(0),
    status: IngestionStatus = IngestionStatus.READY,
    stage: IngestionStage | None = None,
    pages_extracted: int | None = None,
    size_bytes: int = 1024,
    page_count: int = 3,
) -> Document:
    document = Document(
        tenant_id=tenant_id,
        uploader_id=uploader_id,
        name=name,
        size_bytes=size_bytes,
        page_count=page_count,
        content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        storage_key="tenants/x/documents/y.pdf",
        ingestion_status=status,
        deleted_at=(_DELETED_AT if status == IngestionStatus.DELETED else None),
        ingestion_stage=stage,
        pages_extracted=pages_extracted,
        created_at=_NOW - age,
    )
    db_session.add(document)
    await db_session.commit()
    return document


async def test_lists_the_tenants_documents_newest_first_with_their_details(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    db_session.add(Profile(user_id=caller.user_id, first_name="Jane", last_name="Doe"))
    await db_session.commit()
    await _seed(
        db_session,
        tenant_id=caller.tenant_id,
        uploader_id=caller.user_id,
        name="older.pdf",
        age=timedelta(days=2),
    )
    newer = await _seed(
        db_session,
        tenant_id=caller.tenant_id,
        uploader_id=caller.user_id,
        name="newer.pdf",
        status=IngestionStatus.PROCESSING,
        stage=IngestionStage.EXTRACTING,
        pages_extracted=2,
        size_bytes=2048,
        page_count=7,
    )

    response = await client.get(LIST_URL)

    assert response.status_code == 200
    documents = response.json()
    assert [document["name"] for document in documents] == ["newer.pdf", "older.pdf"]
    assert documents[0] == {
        "id": str(newer.id),
        "name": "newer.pdf",
        "size_bytes": 2048,
        "uploader": "Jane Doe",
        "created_at": "2026-09-01T12:00:00Z",
        "ingestion_status": "processing",
        "ingestion_stage": "extracting",
        "pages_extracted": 2,
        "page_count": 7,
    }


async def test_a_document_the_worker_has_not_touched_has_no_stage_or_progress(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    await _seed(
        db_session,
        tenant_id=caller.tenant_id,
        uploader_id=caller.user_id,
        name="fresh.pdf",
        status=IngestionStatus.UPLOADED,
    )

    (document,) = (await client.get(LIST_URL)).json()

    assert document["ingestion_status"] == "uploaded"
    assert document["ingestion_stage"] is None
    assert document["pages_extracted"] is None


async def test_leaves_out_deleted_documents_and_other_tenants_documents(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    other_tenant_id = await make_tenant(db_session)
    other_user_id = await make_user(db_session)
    await _seed(
        db_session,
        tenant_id=caller.tenant_id,
        uploader_id=caller.user_id,
        name="mine.pdf",
    )
    await _seed(
        db_session,
        tenant_id=caller.tenant_id,
        uploader_id=caller.user_id,
        name="gone.pdf",
        status=IngestionStatus.DELETED,
    )
    await _seed(
        db_session,
        tenant_id=other_tenant_id,
        uploader_id=other_user_id,
        name="theirs.pdf",
    )

    response = await client.get(LIST_URL)

    assert [document["name"] for document in response.json()] == ["mine.pdf"]


async def test_names_the_uploader_by_email_or_says_they_left(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    await _seed(
        db_session,
        tenant_id=caller.tenant_id,
        uploader_id=caller.user_id,
        name="by_email.pdf",
        age=timedelta(days=1),
    )
    await _seed(
        db_session,
        tenant_id=caller.tenant_id,
        uploader_id=None,
        name="orphan.pdf",
    )

    by_name = {
        document["name"]: document["uploader"]
        for document in (await client.get(LIST_URL)).json()
    }

    assert by_name["by_email.pdf"].endswith("@example.com")
    assert by_name["orphan.pdf"] == "someone who has since left"


async def test_an_empty_tenant_gets_an_empty_list(client: AsyncClient) -> None:
    response = await client.get(LIST_URL)

    assert response.status_code == 200
    assert response.json() == []


async def test_a_viewer_can_read_the_library(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    caller.role = Role.VIEWER
    await _seed(
        db_session,
        tenant_id=caller.tenant_id,
        uploader_id=caller.user_id,
        name="shared.pdf",
    )

    response = await client.get(LIST_URL)

    assert response.status_code == 200
    assert len(response.json()) == 1


async def test_summary_counts_in_progress_and_failed_documents_like_the_list_shows_them(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    other_tenant_id = await make_tenant(db_session)
    statuses = [
        IngestionStatus.UPLOADED,
        IngestionStatus.PROCESSING,
        IngestionStatus.PROCESSING,
        IngestionStatus.FAILED,
        IngestionStatus.READY,
        IngestionStatus.PARTIAL,
        IngestionStatus.DELETED,
    ]
    for index, status in enumerate(statuses):
        await _seed(
            db_session,
            tenant_id=caller.tenant_id,
            uploader_id=caller.user_id,
            name=f"{index}.pdf",
            status=status,
        )
    await _seed(
        db_session,
        tenant_id=other_tenant_id,
        uploader_id=None,
        name="theirs.pdf",
        status=IngestionStatus.PROCESSING,
    )

    summary = await client.get(SUMMARY_URL)
    listed = (await client.get(LIST_URL)).json()

    assert summary.status_code == 200
    assert summary.json() == {"in_progress": 3, "failed": 1}
    in_list = [document["ingestion_status"] for document in listed]
    assert summary.json() == {
        "in_progress": in_list.count("uploaded") + in_list.count("processing"),
        "failed": in_list.count("failed"),
    }


async def test_summary_of_an_empty_tenant_is_zero(client: AsyncClient) -> None:
    response = await client.get(SUMMARY_URL)

    assert response.status_code == 200
    assert response.json() == {"in_progress": 0, "failed": 0}
