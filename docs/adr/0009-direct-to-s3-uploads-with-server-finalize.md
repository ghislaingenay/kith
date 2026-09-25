---
status: accepted
date: 2026-09-24
---

# Browsers upload PDFs directly to S3; the API finalizes and validates

A PDF reaches storage in three calls. `POST /uploads/init` checks auth, Limits, declared size (20 MB, env), content type and per-Tenant duplicate by declared SHA-256, creates an Upload, and returns a presigned PUT to `pending/{tenant_id}/{upload_id}` (server-generated key, ~10 minute expiry, length and content type signed). The browser PUTs the bytes straight to S3. `POST /uploads/{id}/finalize` downloads the object to a temp file, computes the SHA-256 itself, opens it with pypdfium2 (encrypted, unreadable, or over the page cap is a 422 and the object is deleted), then copies it to `tenants/{tenant_id}/documents/{document_id}.pdf`, creates the Document as `uploaded`, marks the Upload completed, commits, and enqueues Ingestion. This supersedes the "server streams to a temp file, then writes to S3" line in the MVP design.

Why: the API never carries the file bytes, so a 20 MB upload does not hold an API worker for the length of a slow connection, and the provider's buffering `upload` (whole payload in RAM) is not on the path. The alternative, streaming through the API, was simpler and validated before any byte reached S3, but ties API capacity to client bandwidth.

## Consequences

- **Upload is not Document.** An Upload is one transfer attempt (`pending`, `completed`, `expired`, `rejected`) in its own table; the Document is created only at finalize, so rejected and abandoned attempts never appear in Documents, counts, or the dedup index. `uploads.document_id` links them. The arq `job_id` stays the Document id (ADR-0005); the worker never sees the Upload.
- **Finalize is idempotent.** A second call returns the same Document and re-enqueues; the duplicate job collapses on `job_id`. A `tasks` cron re-enqueues Documents stuck in `uploaded`, and expires Uploads still `pending` after 30 minutes (env), deleting their objects.
- **The server's hash is the Content Hash.** The SHA-256 the API computes during finalize is stored and compared with the declared one; a mismatch is rejected as corrupt. The checksum signed into the presigned URL is only an early reject, so finalize does not depend on the store enforcing it. The per-Tenant duplicate check runs again inside the finalize transaction, backed by a unique index on `(tenant_id, content_hash)` over non-deleted Documents.
- **`pending/` is temporary by construction.** A bucket lifecycle rule expires `pending/` after one day as a backstop (`minio-init` adds it in dev); the cron is the primary cleanup. Accepted PDFs are promoted out of `pending/`, so the tenant purge is one prefix delete.
- **Upload limits change.** The per-User "10 uploads/hour" is replaced by a cap of 5 concurrent pending Uploads per User and 30 upload starts per hour per User (both env). Both are counted from the `uploads` table rather than Redis, so a refused start does not count and the retry hint is exact; a pending Upload past its expiry no longer holds a slot. The old limit would block a legitimate 15-file batch, and does not bound the bytes abandoned uploads leave in `pending/`. Documents and storage Limits are checked at `init` for fast feedback and again in the finalize transaction; pending Uploads reserve nothing.
- **The stored PDF is never compressed.** It is the source of truth and the Content Hash is over its bytes.
- **Provider work.** `StorageProvider` needs `copy`, a presigned PUT that can sign content type and length, and a file-based `upload`. boto3 must be configured with `request_checksum_calculation="when_required"`, and an integration test against MinIO covers presigned PUT behaviour.
