---
status: accepted
date: 2026-10-07
---

# Retrieval is hybrid, filters by Tenant and the deleted flag in OpenSearch, checks deleted Documents in Postgres, and falls back to keyword

Search and Ask share one Retrieval: a keyword (BM25) leg and a meaning (kNN on the Query's `voyage-4-large` embedding, ADR-0004) leg, fused by reciprocal rank fusion in an OpenSearch search pipeline. There is no keyword-only or semantic-only mode for the User to pick; which leg found a Chunk is a mechanism, not a choice.

## Decisions

- **`tenant_id` and the `deleted` flag filter the query.** Both legs filter on them, and in the kNN leg the filter sits inside the `knn` clause so Faiss filters during the search. A `bool.filter` around the kNN would drop hits after the top k and return fewer results than asked for. (Amended 2026-10-07: the flag is new. The first version of this decision filtered by `tenant_id` only.)
- **Deleted Documents are flagged in OpenSearch and checked again in Postgres.** Deleting a Document sets `deleted` on its Chunks in the index straight after the Postgres soft delete, and every search leaves flagged Chunks out. This keeps the filter one constant-size clause. The keyword search this replaces sent every live Document id as a `terms` filter, a list that grows with the Tenant and slows the filtered kNN. Retrieval still asks for about 30 hits, joins Document names from Postgres (which it needs anyway), drops hits whose Document is deleted there, and keeps the top 20. Postgres stays the source of truth: a Chunk whose flag was not set (the store was down at delete, or the delete is a moment old) never shows. Setting the flag is best effort and logged if it fails, because the Postgres check already hides the Chunks.
- **Embedding failure falls back to keyword.** If embedding the Query fails or its circuit breaker is open, Retrieval runs the keyword leg alone and marks the result degraded, and the UI says "Showing keyword matches only". A slightly worse result beats an error. The search store itself being down is still an error (503).
- **Chunks without a vector stay findable.** A Document at the `embedding` Ingestion Stage has Chunks with an empty vector field. The kNN leg cannot return them, the keyword leg can, and RRF ranks a Chunk found by one leg. They rank lower until embedded, which matches ADR-0011's "keyword-searchable before `ready`".

## Considered options

- **Keep the live Document id list.** Rejected for request size and kNN filter cost as the Tenant grows.
- **Separate keyword and semantic modes in the UI.** Rejected: it makes the User guess which mechanism suits their Query.

## Consequences

- Fetching ~30 to show 20 means a Tenant with many deleted Documents whose flag was never set could see fewer than 20 results. The flag keeps this rare; raise the over-fetch if it is seen.
- Deleting sets the flag with an update by query, which a concurrent embedding write to the same Chunk can make fail with a version conflict. That is logged, and Postgres still hides the Chunks; the purge job removes them.
- A Chunk indexed before the flag existed has none, which reads as not deleted.
- No rerank yet: RRF order is final until the reranker arrives with Ask (ADR-0004 amendment).
