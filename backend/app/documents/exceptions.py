"""Domain exceptions for the documents domain. Mapped to HTTP in
`exception_handlers.py`."""

import uuid
from datetime import timedelta


class InvalidUploadRequestError(Exception):
    """The declared file can't be uploaded: too large or not a PDF."""


class TooManyPendingUploadsError(Exception):
    """The User already has the most Uploads in progress that they may."""


class UploadRateExceededError(Exception):
    """The User has started the most Uploads they may in the past hour."""

    def __init__(self, message: str, retry_after: timedelta) -> None:
        self.retry_after = retry_after
        super().__init__(message)


class UploadNotFoundError(Exception):
    """No such Upload for this caller in this Tenant. Also raised for
    another Tenant's Upload, so its existence isn't revealed."""

    def __init__(self, upload_id: uuid.UUID) -> None:
        self.upload_id = upload_id
        super().__init__(f"Upload '{upload_id}' not found.")


class UploadObjectMissingError(Exception):
    """Finalize was called before the file reached storage."""


class RefusedUploadError(Exception):
    """The uploaded file can't become a Document. The message is the plain
    reason shown to the person; the Upload is marked rejected with it."""


class UploadSizeMismatchError(RefusedUploadError):
    """The stored object's size differs from the size declared at start."""


class ContentHashMismatchError(RefusedUploadError):
    """The stored object's SHA-256 differs from the one declared at start."""


class UnreadablePdfError(RefusedUploadError):
    """The stored object can't be opened as a PDF."""


class EncryptedPdfError(RefusedUploadError):
    """The PDF is password-protected."""


class TooManyPagesError(RefusedUploadError):
    """The PDF has more pages than the cap."""


class DuplicateDocumentError(RefusedUploadError):
    """A Document with identical content already exists in the Tenant."""


class LimitReachedError(RefusedUploadError):
    """The Tenant's Documents or storage Limit leaves no room for the file."""
