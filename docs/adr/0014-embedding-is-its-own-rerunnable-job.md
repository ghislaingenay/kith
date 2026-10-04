---
status: accepted
date: 2026-10-04
---

# Embedding is its own re-runnable job, after indexing

When a Document's indexing finishes, ingestion enqueues a separate `embed_document` job on the `ingest` queue with job id `embed:{document_id}` (the plain Document id stays the ingestion job's, ADR-0005). The job adds `voyage-4-large` vectors (ADR-0004) to Chunks already in the search index. We split it out instead of continuing inside `ingest_document` because three things need to run embedding alone, without extracting or chunking again: Documents already waiting at `embedding` from before this phase, Chunks that an indexing replay has just made searchable, and a model switch if the Golden Set comparison picks Jina v5.

## What the job does

- It reads the Document first and stops if the Document is deleted.
- It embeds only Chunks whose indexing is done and whose embedding is pending. A Chunk that failed indexing is not in the index, so it cannot take a vector; a Chunk that failed embedding belongs to its dead letter. Running the job twice therefore embeds nothing twice.
- Requests are batched by Voyage's own token count under the 120K-tokens-per-request cap, with `input_type="document"` and truncation off. Chunks are not re-cut (ADR-0011 amendment).
- Vectors are written as partial updates onto the existing index documents. A "not found" there means the Document was deleted mid-job: it is logged and ignored, not recorded as a failure.
- When it finishes, the Document's Ingestion Status is derived from both Chunk statuses: `ready` when every Chunk is indexed and embedded, `partial` when some failed, `failed` when none were made searchable.

## Failure handling

It mirrors indexing (ADR-0011, ADR-0013): three retries with backoff, and a circuit breaker named `embedding` built from `core/circuit_breaker/`. Timeouts, 429 and 5xx answers count as unavailable and are retried. A 400 (a request Voyage would reject the same way again, such as a Chunk over the limit now that truncation is off) is not retried. A batch that still fails marks its Chunks' embedding `failed` and writes a Chunk Dead Letter with stage `embedding`, and the job finishes without raising.

## Commands

- `make embed-documents` enqueues `embed_document` for every Document waiting at `embedding`, or for one `--document-id`. It only enqueues; the worker does the work, under the same retries and breaker.
- `replay_failed_batches` replays open `indexing` dead letters first, then open `embedding` ones; `--stage` limits it to one. A successful indexing replay enqueues `embed_document` for that Document, so the newly indexed Chunks get vectors; if that embedding fails, it becomes a new `embedding` dead letter while the indexing one stays resolved. Each dead letter records one stage's failure.
- A row that fails again stays `open` with its attempt count raised, with no cap, in both stages. Replay is run by a person, who decides when to stop.

## Considered Options

- **Embed inside `ingest_document`, right after indexing.** Simpler, but the backlog, the replay follow-up and a model switch would each need their own path into the middle of that job.
- **Have `make embed-documents` embed in the script process.** Rejected so that every embedding call goes through the worker's retries and breaker.

## Consequences

- Each Document can have two jobs in the queue at once, `{document_id}` and `embed:{document_id}`.
- Embedding tokens are logged per Document but are not Usage (see `CONTEXT.md`).
- Throttling across workers is deferred (ADR-0005 amendment); with one ingest worker, a 429 is handled by the retries and the breaker.
