"""Domain exceptions for the documents domain. Mapped to HTTP in
`exception_handlers.py`."""

import uuid


class InvalidUploadRequestError(Exception):
    """The declared file can't be uploaded: too large or not a PDF."""


class UploadNotFoundError(Exception):
    """No such Upload for this caller in this Tenant. Also raised for
    another Tenant's Upload, so its existence isn't revealed."""

    def __init__(self, upload_id: uuid.UUID) -> None:
        self.upload_id = upload_id
        super().__init__(f"Upload '{upload_id}' not found.")


class UploadObjectMissingError(Exception):
    """Finalize was called before the file reached storage."""


class UploadSizeMismatchError(Exception):
    """The stored object's size differs from the size declared at start."""


class UnreadablePdfError(Exception):
    """The stored object can't be opened as a PDF."""
