"""Fixtures for the documents domain's HTTP tests: the real app and real
Postgres (`db_session`, see tests/conftest.py), with only the caller's
identity, storage and the job queue replaced."""

import hashlib
import io
import uuid
from collections.abc import AsyncIterator

import pypdfium2
import pytest
from pypdf import PdfWriter
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from auth.dependencies import get_current_tenant, get_current_user
from auth.schemas import AuthenticatedUser, TenantContext
from core.jobs.dependencies import get_job_queue
from core.storage.dependencies import get_storage_provider
from documents.dependencies import get_db_session
from main import app
from tenants.models import Tenant
from tenants.permissions import Role
from tests.support.fake_job_queue import FakeJobQueue
from tests.support.fake_storage import FakeStorageProvider
from users.models import User


class Caller:
    """Who the next request is made as: switch `tenant_id`, `user_id` or
    `role` to act as somebody else."""

    def __init__(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.role = Role.MEMBER


async def make_tenant(db_session: AsyncSession) -> uuid.UUID:
    tenant = Tenant(
        name="Acme", slug=f"acme-{uuid.uuid4().hex[:8]}", tier="free", max_users=5
    )
    db_session.add(tenant)
    await db_session.commit()
    return tenant.id


async def make_user(db_session: AsyncSession) -> uuid.UUID:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com", email_verified=True, is_active=True
    )
    db_session.add(user)
    await db_session.commit()
    return user.id


@pytest.fixture
def storage() -> FakeStorageProvider:
    return FakeStorageProvider()


@pytest.fixture
def job_queue() -> FakeJobQueue:
    return FakeJobQueue()


@pytest.fixture
async def caller(db_session: AsyncSession) -> Caller:
    return Caller(await make_tenant(db_session), await make_user(db_session))


@pytest.fixture
async def client(
    db_session: AsyncSession,
    storage: FakeStorageProvider,
    job_queue: FakeJobQueue,
    caller: Caller,
) -> AsyncIterator[AsyncClient]:
    async def _db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = _db_session
    app.dependency_overrides[get_storage_provider] = lambda: storage
    app.dependency_overrides[get_job_queue] = lambda: job_queue
    app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        id=caller.user_id,
        email="jane@example.com",
        email_verified=True,
        is_active=True,
    )
    app.dependency_overrides[get_current_tenant] = lambda: TenantContext(
        tenant_id=caller.tenant_id, role=caller.role
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as http_client:
        yield http_client
    app.dependency_overrides.clear()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_pdf(pages: int = 1) -> bytes:
    pdf = pypdfium2.PdfDocument.new()
    for _ in range(pages):
        pdf.new_page(200, 200)
    buffer = io.BytesIO()
    pdf.save(buffer)
    return buffer.getvalue()


def make_encrypted_pdf() -> bytes:
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.encrypt("secret", algorithm="RC4-128")
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


INIT_URL = "/api/v1/uploads/init"
PDF_CONTENT_TYPE = "application/pdf"


async def init_upload(client: AsyncClient, data: bytes, filename: str = "report.pdf"):
    return await client.post(
        INIT_URL,
        json={
            "filename": filename,
            "size": len(data),
            "content_type": PDF_CONTENT_TYPE,
            "sha256": sha256_hex(data),
        },
    )


async def finalize_upload(client: AsyncClient, upload_id: str):
    return await client.post(f"/api/v1/uploads/{upload_id}/finalize")
