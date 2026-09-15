"""FastAPI dependency wiring for the storage core module."""

from core.container import container
from core.storage.provider import StorageProvider


def get_storage_provider() -> StorageProvider:
    return container.storage_provider()
