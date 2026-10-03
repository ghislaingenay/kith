"""Fixtures for the documents domain's HTTP tests: the real app and real
Postgres (`db_session`, see tests/conftest.py), with only the caller's
identity, storage and the job queue replaced."""

import hashlib
import io
import uuid
from collections.abc import AsyncIterator

import pypdfium2
import pytest
from fpdf import FPDF
from PIL import Image
from pypdf import PdfReader, PdfWriter
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from opensearchpy import AsyncOpenSearch

from auth.dependencies import get_current_tenant, get_current_user
from auth.schemas import AuthenticatedUser, TenantContext
from core.jobs.dependencies import get_job_queue
from core.retry.config import RetrySettings
from core.retry.handler import RetryHandler
from core.storage.dependencies import get_storage_provider
from documents.dependencies import get_db_session
from main import app
from core.search.config import SearchSettings
from core.search.opensearch_index import OpenSearchIndex
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
async def search_index(_opensearch_url: str) -> AsyncIterator[OpenSearchIndex]:
    """The real OpenSearch container, with the shared index created and
    emptied after each test."""
    index = OpenSearchIndex(SearchSettings(search_url=_opensearch_url))
    await index.ensure_index()
    yield index
    await index.close()
    async with AsyncOpenSearch(hosts=[_opensearch_url]) as client:
        await client.indices.delete(index="kith-chunks-*", ignore=[404])


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


def make_text_pdf(pages: list[str]) -> bytes:
    """A PDF with one page per string in `pages`, each page's entire
    content being that string — or nothing, for an empty string, to make
    a genuinely blank page."""
    pdf = FPDF()
    for page_text in pages:
        pdf.add_page()
        if page_text:
            pdf.set_font("helvetica", size=14)
            pdf.cell(text=page_text)
    return bytes(pdf.output())


def make_two_column_pdf(left: str, right: str) -> bytes:
    """A single page with `left` and `right` each written to their own
    half of the page, side by side, the way a two-column layout reads."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    pdf.set_xy(10, 20)
    pdf.multi_cell(w=80, text=left)
    pdf.set_xy(110, 20)
    pdf.multi_cell(w=80, text=right)
    return bytes(pdf.output())


def make_rotated_text_pdf(text: str, rotation: int = 90) -> bytes:
    """A single page holding `text`, rotated by `rotation` degrees via the
    page's `/Rotate` entry. fpdf2 has no page-rotation primitive, so the
    page is built with `make_text_pdf` and then rotated with pypdf, this
    domain's existing dev-only library for structural PDF edits (see
    `make_encrypted_pdf`)."""
    unrotated = make_text_pdf([text])

    reader = PdfReader(io.BytesIO(unrotated))
    writer = PdfWriter()
    page = reader.pages[0]
    page.rotate(rotation)
    writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_image_only_pdf() -> bytes:
    """A single page whose only content is a rasterised image — no text
    layer at all, the way a scanned page looks to a PDF text extractor."""
    image = Image.new("RGB", (100, 100), color=(200, 0, 0))
    image_buffer = io.BytesIO()
    image.save(image_buffer, format="PNG")
    image_buffer.seek(0)

    pdf = FPDF()
    pdf.add_page()
    pdf.image(image_buffer, x=10, y=10, w=50, h=50)
    return bytes(pdf.output())


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


def fast_retry_handler() -> RetryHandler:
    """The real retry handler's three attempts, without the waiting."""
    return RetryHandler(
        RetrySettings(max_attempts=3, base_delay=0, max_delay=0, jitter=False)
    )
