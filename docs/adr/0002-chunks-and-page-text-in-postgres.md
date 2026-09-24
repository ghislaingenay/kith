---
status: accepted
date: 2026-09-14
---

# Chunks and extracted page text live in Postgres; OpenSearch is a derived index

Postgres holds `document_pages` (the text extracted from each PDF page, with how it was extracted and its OCR confidence) and `chunks` (page, ordinal, character offsets, text hash, embedding status, error). OpenSearch holds only what search needs: Chunk text plus vector. The original PDF in S3 is the source of truth; everything else is regenerable from it.

The obvious alternative was OpenSearch as the only store for Chunks. We rejected it because two required behaviours need Chunk records that outlive an index: retrying only the Chunks whose embedding failed (an Ingestion Status of `partial`), and re-chunking with new parameters or a new embedding model without paying for OCR again. At the MVP's Limits (20 Documents per Tenant, 100 pages per Document) the extra rows in Postgres are tens of megabytes at worst; page text moves to S3 behind the same repository interface if that ever changes.

## Consequences

- Ingestion Status is derived from Chunk statuses, not set directly.
- A Retrieval hit is joined back to its Chunk row for Citations, so Postgres and OpenSearch must agree on Chunk ids.
- Rebuilding OpenSearch from scratch is a reindex job over Postgres plus an embedding pass; no OpenSearch backups are taken.
