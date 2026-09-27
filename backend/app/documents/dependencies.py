"""FastAPI dependency wiring for the documents domain."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import container
from core.database import get_session
from core.jobs.dependencies import get_job_queue
from core.jobs.provider import JobQueue
from core.storage.dependencies import get_storage_provider
from core.storage.provider import StorageProvider
from documents.config import UploadSettings
from documents.deletion_service import DocumentDeletionService
from documents.library_service import DocumentLibraryService
from documents.repository import DocumentsRepository
from documents.service import DocumentUploadService


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session(container.db_session_factory()):
        yield session


def get_upload_settings() -> UploadSettings:
    return container.upload_settings()


def get_documents_repository(
    session: AsyncSession = Depends(get_db_session),
) -> DocumentsRepository:
    return DocumentsRepository(session)


def get_upload_service(
    repository: Annotated[DocumentsRepository, Depends(get_documents_repository)],
    storage: Annotated[StorageProvider, Depends(get_storage_provider)],
    job_queue: Annotated[JobQueue, Depends(get_job_queue)],
    settings: Annotated[UploadSettings, Depends(get_upload_settings)],
) -> DocumentUploadService:
    return DocumentUploadService(repository, storage, job_queue, settings)


def get_library_service(
    repository: Annotated[DocumentsRepository, Depends(get_documents_repository)],
) -> DocumentLibraryService:
    return DocumentLibraryService(repository)


def get_deletion_service(
    repository: Annotated[DocumentsRepository, Depends(get_documents_repository)],
    job_queue: Annotated[JobQueue, Depends(get_job_queue)],
) -> DocumentDeletionService:
    return DocumentDeletionService(repository, job_queue)
