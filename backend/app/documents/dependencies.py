"""FastAPI dependency wiring for the documents domain."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.container import container
from core.database import get_session
from core.jobs.dependencies import get_job_queue
from core.jobs.provider import JobQueue
from core.embedding.provider import EmbeddingProvider
from core.rerank.config import RerankSettings
from core.rerank.dependencies import get_rerank_settings, get_reranker
from core.rerank.provider import Reranker
from core.search.dependencies import get_query_embedding_provider, get_search_index
from core.search.provider import SearchIndex
from core.storage.dependencies import get_storage_provider
from core.storage.provider import StorageProvider
from documents.config import PreviewSettings, RetrievalSettings, UploadSettings
from documents.deletion_service import DocumentDeletionService
from documents.file_service import DocumentFileService
from documents.library_service import DocumentLibraryService
from documents.repository import DocumentsRepository
from documents.retrieval_service import RetrievalService
from documents.service import DocumentUploadService


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async for session in get_session(container.db_session_factory()):
        yield session


def get_upload_settings() -> UploadSettings:
    return container.upload_settings()


def get_retrieval_settings() -> RetrievalSettings:
    return container.retrieval_settings()


def get_preview_settings() -> PreviewSettings:
    return container.preview_settings()


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


def get_file_service(
    repository: Annotated[DocumentsRepository, Depends(get_documents_repository)],
    storage: Annotated[StorageProvider, Depends(get_storage_provider)],
    settings: Annotated[PreviewSettings, Depends(get_preview_settings)],
) -> DocumentFileService:
    return DocumentFileService(repository, storage, settings)


def get_deletion_service(
    repository: Annotated[DocumentsRepository, Depends(get_documents_repository)],
    job_queue: Annotated[JobQueue, Depends(get_job_queue)],
    search_index: Annotated[SearchIndex, Depends(get_search_index)],
) -> DocumentDeletionService:
    return DocumentDeletionService(repository, job_queue, search_index)


def get_retrieval_service(
    repository: Annotated[DocumentsRepository, Depends(get_documents_repository)],
    search_index: Annotated[SearchIndex, Depends(get_search_index)],
    embedding_provider: Annotated[
        EmbeddingProvider | None, Depends(get_query_embedding_provider)
    ],
    settings: Annotated[RetrievalSettings, Depends(get_retrieval_settings)],
    reranker: Annotated[Reranker | None, Depends(get_reranker)],
    rerank_settings: Annotated[RerankSettings, Depends(get_rerank_settings)],
) -> RetrievalService:
    return RetrievalService(
        repository,
        search_index,
        embedding_provider,
        settings,
        reranker,
        rerank_settings,
    )
