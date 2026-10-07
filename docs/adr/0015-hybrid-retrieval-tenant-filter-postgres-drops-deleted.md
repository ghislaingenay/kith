---
status: accepted
date: 2026-10-07
---

# Retrieval is hybrid, filters by Tenant in OpenSearch, drops deleted Documents in Postgres, and falls back to keyword

Search and Ask share one Retrieval: a keyword (BM25) leg and a meaning (kNN on the Query's `voyage-4-large` embedding, ADR-0004) leg, fused by reciprocal rank fusion in an OpenSearch search pipeline. There is no keyword-only or semantic-only mode for the User to pick; which leg found a Chunk is a mechanism, not a choice.

## Decisions

- **Only `tenant_id` filters the query.** Both legs filter on it, and in the kNN leg the filter sits inside the `knn` clause so Faiss filters during the search. A `bool.filter` around the kNN would drop hits after the top k and return fewer results than asked for.
- **Deleted Documents are dropped in Postgres, not in OpenSearch.** The keyword search this replaces sent every live Document id as a `terms` filter. That list grows with the Tenant and slows the filtered kNN. Instead Retrieval asks for about 30 hits, joins Document names from Postgres (which it needs anyway), drops hits whose Document is deleted, and keeps the top 20. Postgres stays the only source of truth for what is deleted, so a Chunk whose index cleanup lagged behind the delete never shows.
- **Embedding failure falls back to keyword.** If embedding the Query fails or its circuit breaker is open, Retrieval runs the keyword leg alone and marks the result degraded, and the UI says "Showing keyword matches only". A slightly worse result beats an error. The search store itself being down is still an error (503).
- **Chunks without a vector stay findable.** A Document at the `embedding` Ingestion Stage has Chunks with an empty vector field. The kNN leg cannot return them, the keyword leg can, and RRF ranks a Chunk found by one leg. They rank lower until embedded, which matches ADR-0011's "keyword-searchable before `ready`".

## Considered options

- **Keep the live Document id list.** Rejected for request size and kNN filter cost as the Tenant grows.
- **Separate keyword and semantic modes in the UI.** Rejected: it makes the User guess which mechanism suits their Query.

## Consequences

- Fetching ~30 to show 20 means a Tenant with many deleted-but-still-indexed Chunks could see fewer than 20 results. Index cleanup on delete keeps this rare; raise the over-fetch if it is seen.
- No rerank yet: RRF order is final until the reranker arrives with Ask (ADR-0004 amendment).
