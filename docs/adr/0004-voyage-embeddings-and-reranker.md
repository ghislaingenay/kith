---
status: accepted
date: 2026-09-14
---

# Voyage `voyage-4-large` for embeddings and `rerank-2.5` for reranking

Embeddings are produced by Voyage `voyage-4-large` at 1024 dimensions and Retrieval results are reranked by Voyage `rerank-2.5`, both behind provider interfaces (`EmbeddingProvider`, `Reranker`). Decided from the comparison in `docs/research/embedding-and-reranker-choice.md` (vendor pages read 2026-09-14): Voyage documents the model as optimised for multilingual retrieval, 1024 is its native default dimension, the first 200M tokens are free so the seed corpus and evals cost nothing, entry-tier rate limits fit a small worker, and one official SDK covers embed and rerank.

Rejected: OpenAI `text-embedding-3-large` (1024 only by truncation, weakest documented multilingual score), Cohere (per-token prices no longer public, trial keys non-commercial), Jina v5 (strong runner-up, but no verified official Python SDK and the tightest free-tier throughput), Mistral embed (no multilingual or rate-limit documentation).

## Consequences

- The OpenSearch mapping is `knn_vector`, dimension 1024, `cosinesimil`, HNSW on the Faiss engine; hybrid search with reciprocal rank fusion requires OpenSearch 2.19 or later.
- The embedding model id is part of the index name (see ADR-0001); changing model means a new index and a reindex.
- Voyage publishes no language list for the v4 family, so the Golden Set must cover the languages the team actually uses (English and French at minimum) and be run against Jina v5 as a second candidate before this decision is treated as final.
- The worker batches embedding requests by token count, not only by text count, because of the per-request token cap.
