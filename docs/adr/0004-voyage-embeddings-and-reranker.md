---
status: accepted
date: 2026-09-14
amended: 2026-10-04
---

# Voyage `voyage-4-large` for embeddings and `rerank-2.5` for reranking

Embeddings are produced by Voyage `voyage-4-large` at 1024 dimensions and Retrieval results are reranked by Voyage `rerank-2.5`, both behind provider interfaces (`EmbeddingProvider`, `Reranker`). Decided from the comparison in `docs/research/embedding-and-reranker-choice.md` (vendor pages read 2026-09-14): Voyage documents the model as optimised for multilingual retrieval, 1024 is its native default dimension, the first 200M tokens are free so the seed corpus and evals cost nothing, entry-tier rate limits fit a small worker, and one official SDK covers embed and rerank.

Rejected: OpenAI `text-embedding-3-large` (1024 only by truncation, weakest documented multilingual score), Cohere (per-token prices no longer public, trial keys non-commercial), Jina v5 (strong runner-up, but no verified official Python SDK and the tightest free-tier throughput), Mistral embed (no multilingual or rate-limit documentation).

## Consequences

- The OpenSearch mapping is `knn_vector`, dimension 1024, `cosinesimil`, HNSW on the Faiss engine; hybrid search with reciprocal rank fusion requires OpenSearch 2.19 or later.
- The embedding model id is part of the index name (see ADR-0012); changing model means a new index and a reindex.
- Voyage publishes no language list for the v4 family, so the Golden Set must cover the languages the team actually uses (English and French at minimum) and be run against Jina v5 as a second candidate before this decision is treated as final.
- The worker batches embedding requests by token count, not only by text count, because of the per-request token cap.

> Amended 2026-10-04, before building the embedding phase (ADR-0014). The Golden Set does not exist yet, so we build on `voyage-4-large` now and keep the English and French comparison against Jina v5 as the gate before this decision is final; switching later is one re-embedding job, free within the first 200M tokens. Three points are now fixed:
>
> - **Queries use the same model.** Voyage 4 models share one vector space, so Queries could use `voyage-4-lite`, but a Query is a few tokens and one model id means one less thing to rule out when results look wrong. Revisit only if Query latency becomes a problem.
> - **Truncation is off** (`truncation=False`). A Chunk is about 500 tokens against a 32,000-token limit, so an over-long one means a chunker bug; it should fail into a Chunk Dead Letter, not become a vector of part of its text.
> - **The reranker is chosen in the Retrieval phase**, not here. Since this ADR, `rerank-3` (in preview, 200M free tokens, no multilingual claim) has appeared beside `rerank-2.5`; the Golden Set decides between them together with hybrid search.
>
> The Voyage account needs a payment method on file to get Tier 1 limits, which are the only ones Voyage publishes.

> Amended 2026-10-08, before building Rerank. The reranker is **`rerank-3`**, with the model id in the `RERANK_MODEL` setting so it can change without code. Since the previous amendment Voyage released it as generally available (2026-09-30) and moved `rerank-2.5` to "Older models"; its launch post evaluates it on 31 languages, ahead of `rerank-2.5`, at the same $0.05 per 1M tokens with the first 200M free (the pricing page is inconsistent on the free tokens; check the billing dashboard). It uses the same `voyageai` SDK and API key, and its scores keep `rerank-2.5`'s scale. Truncation is off, as for embeddings: a Query and a ~500-token Chunk are far under the 32,000-token context, so an over-long input means a bug. French is not named in any Voyage reranker claim, so the Golden Set still has the last word, as for the embedding model. Sources read 2026-10-08: https://docs.voyageai.com/docs/reranker , https://docs.voyageai.com/docs/pricing , https://blog.voyageai.com/2026/09/30/rerank-3/ .
