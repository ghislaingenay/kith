"""HTTP tests for the Tenant's Limits on uploads: checked at start for fast
feedback and again, authoritatively, at finalize."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from collections.abc import AsyncIterator

from httpx import AsyncClient
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import create_session_factory
from core.storage.dependencies import get_storage_provider
from documents.config import UploadSettings
from documents.dependencies import get_db_session, get_upload_settings
from documents.models import Document, IngestionStatus, Upload
from main import app
from tests.documents.conftest import (
    Caller,
    make_pdf,
    make_tenant,
    make_user,
    sha256_hex,
)
from tests.support.fake_storage import FakeStorageProvider

_INIT_URL = "/api/v1/uploads/init"
_PDF_CONTENT_TYPE = "application/pdf"
_MB = 1024 * 1024


def _limits(**env: int) -> None:
    app.dependency_overrides[get_upload_settings] = lambda: UploadSettings(**env)


async def _init(client: AsyncClient, data: bytes, filename: str = "report.pdf"):
    return await client.post(
        _INIT_URL,
        json={
            "filename": filename,
            "size": len(data),
            "content_type": _PDF_CONTENT_TYPE,
            "sha256": sha256_hex(data),
        },
    )


async def _finalize(client: AsyncClient, upload_id: str):
    return await client.post(f"/api/v1/uploads/{upload_id}/finalize")


async def _start_and_send(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller, data: bytes
) -> str:
    """An Upload that passed start and whose bytes reached storage."""
    response = await _init(client, data)
    assert response.status_code == 201, response.text
    upload_id = response.json()["upload_id"]
    storage.put_object(f"pending/{caller.tenant_id}/{upload_id}", data)
    return upload_id


async def _add_document(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller, pages: int
) -> None:
    """Uploads a PDF of `pages` blank pages; each page count is distinct
    content, so none is a duplicate of another."""
    data = make_pdf(pages=pages)
    upload_id = (await _init(client, data)).json()["upload_id"]
    storage.put_object(f"pending/{caller.tenant_id}/{upload_id}", data)
    response = await _finalize(client, upload_id)
    assert response.status_code == 200, response.text


async def _seed_document(
    db_session: AsyncSession,
    caller: Caller,
    *,
    size_bytes: int,
    status: IngestionStatus = IngestionStatus.READY,
) -> None:
    """A Document that already exists, without going through an upload."""
    db_session.add(
        Document(
            tenant_id=caller.tenant_id,
            uploader_id=caller.user_id,
            name="existing.pdf",
            size_bytes=size_bytes,
            page_count=1,
            content_hash=uuid.uuid4().hex + uuid.uuid4().hex,
            storage_key="tenants/x/documents/y.pdf",
            ingestion_status=status,
        )
    )
    await db_session.commit()


async def test_start_is_refused_at_the_documents_limit(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    _limits(UPLOAD_MAX_DOCUMENTS=2)
    await _add_document(client, storage, caller, pages=1)
    await _add_document(client, storage, caller, pages=2)

    response = await _init(client, make_pdf(pages=3))

    assert response.status_code == 409
    assert response.json()["message"] == (
        "Your workspace has reached its limit of 2 documents. "
        "Delete a document to upload another."
    )
    assert len(storage.presigned_puts) == 2, "no link is signed for a refused start"


async def test_start_is_refused_when_the_file_would_pass_the_storage_limit(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    await _seed_document(db_session, caller, size_bytes=99 * _MB)
    over = b"x" * (_MB + 1)

    response = await _init(client, over)

    assert response.status_code == 409
    assert response.json()["message"] == (
        "This file would take your workspace over its storage limit of 100 MB. "
        "Delete a document to make room."
    )


async def test_a_file_that_exactly_fills_the_storage_limit_is_accepted(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    await _seed_document(db_session, caller, size_bytes=99 * _MB)

    response = await _init(client, b"x" * _MB)

    assert response.status_code == 201


async def test_deleted_documents_count_toward_neither_limit(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    _limits(UPLOAD_MAX_DOCUMENTS=1)
    await _seed_document(
        db_session, caller, size_bytes=100 * _MB, status=IngestionStatus.DELETED
    )

    response = await _init(client, make_pdf(pages=1))

    assert response.status_code == 201


async def test_a_pending_upload_reserves_nothing(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    _limits(UPLOAD_MAX_DOCUMENTS=1)
    assert (await _init(client, make_pdf(pages=1))).status_code == 201

    response = await _init(client, make_pdf(pages=2))

    assert response.status_code == 201


async def test_finalize_refuses_the_upload_that_no_longer_fits_the_documents_limit(
    client: AsyncClient,
    storage: FakeStorageProvider,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    _limits(UPLOAD_MAX_DOCUMENTS=1)
    first = await _start_and_send(client, storage, caller, make_pdf(pages=1))
    second = await _start_and_send(client, storage, caller, make_pdf(pages=2))
    await _finalize(client, first)

    refused = await _finalize(client, second)

    assert refused.status_code == 409
    assert "limit of 1 document" in refused.json()["message"]
    assert not any(key.startswith("pending/") for key in storage.keys)
    documents = await db_session.scalar(select(func.count()).select_from(Document))
    assert documents == 1


async def test_finalize_refuses_the_upload_that_no_longer_fits_the_storage_limit(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    one, two = make_pdf(pages=1), make_pdf(pages=2)
    _limits(UPLOAD_MAX_STORAGE_BYTES=len(one) + len(two) - 1)
    first = await _start_and_send(client, storage, caller, one)
    second = await _start_and_send(client, storage, caller, two)
    await _finalize(client, first)

    refused = await _finalize(client, second)

    assert refused.status_code == 409
    assert "storage limit" in refused.json()["message"]


async def test_finalizing_an_upload_refused_for_a_limit_again_repeats_the_conflict(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    _limits(UPLOAD_MAX_DOCUMENTS=1)
    first = await _start_and_send(client, storage, caller, make_pdf(pages=1))
    second = await _start_and_send(client, storage, caller, make_pdf(pages=2))
    await _finalize(client, first)
    refused = await _finalize(client, second)

    again = await _finalize(client, second)

    assert again.status_code == 409
    assert again.json()["message"] == refused.json()["message"]


class _StorageThatMakesDownloadsMeet(FakeStorageProvider):
    """Holds each download until `parties` have started one, so parallel
    finalizes are all past the file check before any of them gets further."""

    def __init__(self, parties: int) -> None:
        super().__init__()
        self._parties = parties
        self._arrived = 0
        self._all_arrived = asyncio.Event()

    async def download(self, key: str):
        self._arrived += 1
        if self._arrived >= self._parties:
            self._all_arrived.set()
        await self._all_arrived.wait()
        async for chunk in super().download(key):
            yield chunk


async def test_two_parallel_uploads_that_both_passed_start_but_fit_only_once(
    client: AsyncClient,
    db_session: AsyncSession,
    caller: Caller,
) -> None:
    storage = _StorageThatMakesDownloadsMeet(parties=2)
    app.dependency_overrides[get_storage_provider] = lambda: storage
    _limits(UPLOAD_MAX_DOCUMENTS=1)
    first = await _start_and_send(client, storage, caller, make_pdf(pages=1))
    second = await _start_and_send(client, storage, caller, make_pdf(pages=2))
    # Each request needs its own session: one AsyncSession can't run two
    # transactions at once.
    session_factory = create_session_factory(db_session.bind)

    async def _session_per_request() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db_session] = _session_per_request

    responses = await asyncio.gather(_finalize(client, first), _finalize(client, second))

    assert sorted(response.status_code for response in responses) == [200, 409]
    documents = await db_session.scalar(select(func.count()).select_from(Document))
    assert documents == 1
    outcomes = await db_session.scalars(select(Upload.status))
    assert sorted(outcomes) == ["completed", "rejected"]
    permanent_objects = [key for key in storage.keys if key.startswith("tenants/")]
    assert len(permanent_objects) == 1


async def _backdate_uploads(db_session: AsyncSession, age: timedelta) -> None:
    await db_session.execute(
        update(Upload).values(created_at=datetime.now(UTC) - age)
    )
    await db_session.commit()


async def test_a_sixth_concurrent_pending_upload_is_refused(
    client: AsyncClient,
) -> None:
    for pages in range(1, 6):
        assert (await _init(client, make_pdf(pages=pages))).status_code == 201

    response = await _init(client, make_pdf(pages=6))

    assert response.status_code == 429
    assert response.json()["message"] == (
        "You already have 5 uploads in progress. "
        "Wait for one to finish, then try again."
    )


async def test_completing_a_pending_upload_frees_a_slot(
    client: AsyncClient, storage: FakeStorageProvider, caller: Caller
) -> None:
    _limits(UPLOAD_MAX_PENDING_PER_USER=2)
    first = await _start_and_send(client, storage, caller, make_pdf(pages=1))
    await _start_and_send(client, storage, caller, make_pdf(pages=2))
    assert (await _init(client, make_pdf(pages=3))).status_code == 429

    await _finalize(client, first)

    assert (await _init(client, make_pdf(pages=3))).status_code == 201


async def test_an_expired_upload_frees_a_slot(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _limits(UPLOAD_MAX_PENDING_PER_USER=1)
    assert (await _init(client, make_pdf(pages=1))).status_code == 201
    assert (await _init(client, make_pdf(pages=2))).status_code == 429

    await db_session.execute(update(Upload).values(status="expired"))
    await db_session.commit()

    assert (await _init(client, make_pdf(pages=2))).status_code == 201


async def test_an_abandoned_upload_stops_counting_once_it_is_past_its_expiry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _limits(UPLOAD_MAX_PENDING_PER_USER=1, UPLOAD_PENDING_EXPIRY_SECONDS=1800)
    assert (await _init(client, make_pdf(pages=1))).status_code == 201

    await _backdate_uploads(db_session, timedelta(minutes=31))

    assert (await _init(client, make_pdf(pages=2))).status_code == 201


async def test_the_pending_cap_is_per_user(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    _limits(UPLOAD_MAX_PENDING_PER_USER=1)
    assert (await _init(client, make_pdf(pages=1))).status_code == 201
    assert (await _init(client, make_pdf(pages=2))).status_code == 429

    caller.user_id = await make_user(db_session)

    assert (await _init(client, make_pdf(pages=2))).status_code == 201


async def test_the_start_after_the_hourly_allowance_is_refused_with_a_retry_hint(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _limits(UPLOAD_MAX_STARTS_PER_HOUR=3, UPLOAD_MAX_PENDING_PER_USER=99)
    for pages in range(1, 4):
        assert (await _init(client, make_pdf(pages=pages))).status_code == 201
    # The oldest start happened 58 minutes ago, so a slot frees in 2 minutes.
    await db_session.execute(
        update(Upload)
        .where(Upload.created_at == select(func.min(Upload.created_at)).scalar_subquery())
        .values(created_at=datetime.now(UTC) - timedelta(minutes=58))
    )
    await db_session.commit()

    response = await _init(client, make_pdf(pages=4))

    assert response.status_code == 429
    assert response.json()["message"] == (
        "You have started too many uploads this hour. Try again in 2 minutes."
    )
    assert 60 < int(response.headers["Retry-After"]) <= 120


async def test_starts_older_than_an_hour_no_longer_count(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    _limits(UPLOAD_MAX_STARTS_PER_HOUR=2, UPLOAD_MAX_PENDING_PER_USER=99)
    for pages in range(1, 3):
        assert (await _init(client, make_pdf(pages=pages))).status_code == 201

    await _backdate_uploads(db_session, timedelta(minutes=61))

    assert (await _init(client, make_pdf(pages=3))).status_code == 201


async def test_the_hourly_allowance_is_per_user(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    _limits(UPLOAD_MAX_STARTS_PER_HOUR=1, UPLOAD_MAX_PENDING_PER_USER=99)
    assert (await _init(client, make_pdf(pages=1))).status_code == 201
    assert (await _init(client, make_pdf(pages=2))).status_code == 429

    caller.user_id = await make_user(db_session)

    assert (await _init(client, make_pdf(pages=2))).status_code == 201


async def test_another_tenants_documents_do_not_count_toward_this_tenants_limits(
    client: AsyncClient, db_session: AsyncSession, caller: Caller
) -> None:
    _limits(UPLOAD_MAX_DOCUMENTS=1)
    await _seed_document(db_session, caller, size_bytes=100 * _MB)
    caller.tenant_id = await make_tenant(db_session)

    response = await _init(client, make_pdf(pages=1))

    assert response.status_code == 201
