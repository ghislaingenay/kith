---
status: accepted
date: 2026-09-14
---

# One OpenSearch index per Tenant

Every Tenant gets its own OpenSearch index, named by Tenant id, embedding model id and mapping version (`kith-{tenant_id}-{model_id}-v{mapping_version}`), created when the Tenant is created. The obvious alternative is one shared index with a mandatory `tenant_id` filter on every query. We chose per-Tenant indices because isolation then cannot be forgotten by a missing filter, and because re-embedding one Tenant with a new model becomes "build a new index, swap the alias" rather than a filtered delete-and-reinsert inside a live shared index. With one Tenant today the cost is nil; the naming convention is the only thing that must be honoured.

## Consequences

- Index mappings are versioned in code; a change to the embedding model or the mapping means a new index and a reindex job, never an in-place edit.
- Purging a Tenant is deleting one index.
- Cross-Tenant search is impossible by construction, which is intended.

## Index shape (amended 2026-10-02, issue #50)

- **Name and alias.** The model id is normalized to lowercase letters, digits and hyphens (`voyage-4-large-1024`). The version is in the name so a reindex for a mapping change can build the new index beside the old one while both are alive, then swap the alias. The application only ever talks to the alias `kith-{tenant_id}`. `mapping_version` is also stored in the index's `_meta` so tooling can find indices that are out of date.
- **Fields.** Each indexed Chunk has `text` (analyzed with the ADR-0011 chain, same analyzer for indexing and searching), `embedding` (`knn_vector`, 1024, `cosinesimil`, HNSW on Faiss, `m` 16, `ef_construction` 100, default `ef_search`), `document_id` (keyword) and `page_number` (integer). The document id is the Chunk's Postgres id (ADR-0002). Everything else (filename, upload time, tags) is joined from Postgres, because a field repeated on every Chunk cannot change without a reindex and nothing in the MVP searches or filters on it. `tenant_id` is not a field: the index is already per Tenant.
- **Strict.** `dynamic` is `strict`, so an unknown field is rejected; adding a field is a new mapping version.
- **Vectors stay in `_source`**, so a reindex is a plain `_reindex` call and does not pay for embeddings again, at the cost of storage.
- **Settings.** `knn: true`, 1 shard, 0 replicas in development (replicas are a deploy-time setting), default refresh interval. The worker refreshes the index once when a Document's indexing finishes, so the Document is searchable as its stage ends.
- **Deleting a Document** deletes its Chunks from the index (by `document_id`) rather than flagging them, so no query has to remember a filter.
- **No synonyms** and so no separate search analyzer; adding one is a new mapping version.
