---
status: accepted
date: 2026-09-27
---

# Extraction outcome is judged by page success ratio, not exceptions; pages are never versioned

A page's extraction only fails when the extraction call itself throws; empty text from a call that succeeded (a blank page, a scan with no text layer) is not a failure. Whether a Document as a whole succeeds is decided by `successful_pages / total_pages` against a configurable minimum (`INGESTION_MIN_EXTRACTION_SUCCESS_RATIO`, default 0.8): below it, the Document is marked `failed` with a reason in `ingestion_error`, and `ingestion_stage` is left at `extracting` to say where it failed — no new status or stage value is introduced. At or above the threshold, the Document stays `processing`/`chunking`, an intentional "waiting for a stage that doesn't exist yet" state, since chunking isn't built. That below-threshold outcome is handled entirely inside the job and never raises, so the worker queue's automatic retry — meant for transient infrastructure failures such as storage or the database being unreachable — never fires against a static file that would produce the identical result on every attempt. `document_pages` keeps no history: the source PDF in S3 is the only source of truth (ADR-0002), so any retry is a full re-extraction of every page via an upsert on `(document_id, page_number)`, never a partial resume.

## Consequences

- A page-level extraction error never raises out of the job by itself; only a below-threshold ratio or a genuine infrastructure error changes the Document's terminal state or triggers the queue's automatic retry.
- `document_pages` rows always reflect only the latest extraction attempt; nothing here preserves what a prior attempt produced.
- Changing the success-ratio threshold, or how a page-level failure is detected, can flip a Document between `failed` and `processing` on its next retry with no data migration — it's a behavior/config change, not a schema change.
