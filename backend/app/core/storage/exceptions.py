"""Provider-agnostic exceptions for the storage abstraction."""


class StorageError(Exception):
    """Base exception for all storage provider failures."""


class StorageObjectNotFoundError(StorageError):
    """Raised when an object does not exist at the given key."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Object not found: {key}")


class StoragePermissionError(StorageError):
    """Raised when the provider denies access to an object or bucket."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Permission denied for object: {key}")


class StorageConfigurationError(StorageError):
    """Raised when required provider configuration is missing or invalid."""
