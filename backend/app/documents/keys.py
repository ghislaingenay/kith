"""Object-key layout for uploads. Keys are server-generated and never
contain the client's filename."""

import uuid


def pending_upload_key(tenant_id: uuid.UUID, upload_id: uuid.UUID) -> str:
    """Where the browser PUTs the file, until finalize promotes it."""
    return f"pending/{tenant_id}/{upload_id}"


def document_key(tenant_id: uuid.UUID, document_id: uuid.UUID) -> str:
    """A Document's permanent object, under its Tenant's prefix."""
    return f"tenants/{tenant_id}/documents/{document_id}.pdf"
