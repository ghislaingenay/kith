---
status: accepted
date: 2026-10-02
supersedes: ADR-0001
---

# One shared OpenSearch index for all Tenants, with `tenant_id` on every Chunk

All Tenants' Chunks live in one OpenSearch index, and every Chunk carries its `tenant_id`. This replaces ADR-0001's one index per Tenant. ADR-0001 chose per-Tenant indices so a missing filter could not leak across Tenants, and so one Tenant could be re-embedded alone. We reverse it because the costs it did not weigh are real here: an index to create on signup (so signup depends on the search store), a boot check and a backfill script per Tenant, an alias per Tenant, and many tiny indices at scale. The benefit is smaller than it looked: ADR-0004 fixes one embedding model for everyone, so a model change reindexes every Tenant anyway.

## Index shape

- **Name and alias.** The index is `kith-chunks-{model_id}-v{mapping_version}` (model id lowercase letters, digits and hyphens, e.g. `kith-chunks-voyage-4-large-1024-v2`). The version is in the name so a reindex for a mapping change can build the new index beside the old one and swap the alias. The application only talks to the alias `kith-chunks`. `mapping_version` is also stored in the index's `_meta`.
- **Fields.** `text` (analyzed with the ADR-0011 chain, same analyzer for indexing and searching), `embedding` (`knn_vector`, 1024, `cosinesimil`, HNSW on Faiss, `m` 16, `ef_construction` 100, default `ef_search`), `tenant_id` (keyword), `document_id` (keyword), `page_number` (integer), `ordinal` (integer, the Chunk's position in its Document). The document id is the Chunk's Postgres id (ADR-0002). Filename, upload time and tags are joined from Postgres, because a field repeated on every Chunk cannot change without a reindex and nothing in the MVP searches or filters on it.
- **Strict.** `dynamic` is `strict`; adding a field is a new mapping version.
- **Vectors stay in `_source`**, so a reindex is a plain `_reindex` call and does not pay for embeddings again, at the cost of storage.
- **Settings.** `knn: true`, 1 shard, 0 replicas in development (replicas are a deploy-time setting), default refresh interval. The worker refreshes once when a Document's indexing finishes. Documents are indexed with `routing` set to the Tenant id, so a Tenant's Chunks stay on one shard if shards are added.
- **No synonyms**, so no separate search analyzer; adding one is a new mapping version.

## Isolation

Isolation now rests on a filter, not on structure. One search-index interface is the only code that talks to OpenSearch, and it adds `tenant_id` (and the routing) to every query, count, delete and bulk write; callers pass a Tenant id and cannot omit it. A test asserts that a query for one Tenant never returns another Tenant's Chunk.

## Lifecycle

- A script (`make search-index-create`) creates the index and alias if absent; running it twice changes nothing.
- The API checks at startup that the alias exists and refuses to start if it does not, naming the script to run. Tenant creation does not touch OpenSearch.
- Deleting a Document deletes its Chunks from the index by `document_id` (scoped by `tenant_id`) rather than flagging them. Purging a Tenant deletes by `tenant_id`.
- A change to the embedding model or the mapping means a new versioned index and a reindex job, never an in-place edit.

## Consequences

- One re-embedding or mapping change reindexes all Tenants together.
- A bug in the interface's filter could leak across Tenants; the isolation test is the guard.
- BM25 statistics are shared across Tenants, so one Tenant's text slightly affects another's ranking.
