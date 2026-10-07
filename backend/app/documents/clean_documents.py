"""Removes every Document for development: their rows, their files in storage
and the search index. Run with `make clean-documents`; see
`docs/search-quickstart.md`."""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import async_sessionmaker

from core.search.provider import SearchIndex
from core.storage.provider import StorageProvider
from documents.keys import pending_upload_key
from documents.repository import DocumentsRepository


@dataclass(frozen=True)
class CleanResult:
    documents: int
    uploads: int


async def clean_documents(
    session_factory: async_sessionmaker,
    storage: StorageProvider,
    search_index: SearchIndex,
) -> CleanResult:
    """Deletes the files first, then the rows, then the index. Deleting a file
    that is gone is not an error, so a run that stopped part-way can be run
    again; the other order would lose the keys of files not yet deleted. Only
    the objects the rows point to are deleted, never the rest of the storage."""
    async with session_factory() as session:
        repository = DocumentsRepository(session)
        keys = await repository.list_every_document_storage_key()
        keys += [
            pending_upload_key(tenant_id, upload_id)
            for tenant_id, upload_id in await repository.list_every_upload_reference()
        ]
        for key in keys:
            await storage.delete(key)
        documents, uploads = await repository.delete_every_upload_and_document()
    await search_index.recreate_index()
    return CleanResult(documents=documents, uploads=uploads)
