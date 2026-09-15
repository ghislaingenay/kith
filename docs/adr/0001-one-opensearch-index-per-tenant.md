---
status: accepted
date: 2026-09-14
---

# One OpenSearch index per Tenant

Every Tenant gets its own OpenSearch index, named by Tenant id and embedding model id, created when the Tenant is created. The obvious alternative is one shared index with a mandatory `tenant_id` filter on every query. We chose per-Tenant indices because isolation then cannot be forgotten by a missing filter, and because re-embedding one Tenant with a new model becomes "build a new index, swap the alias" rather than a filtered delete-and-reinsert inside a live shared index. With one Tenant today the cost is nil; the naming convention is the only thing that must be honoured.

## Consequences

- Index mappings are versioned in code; a change to the embedding model or the mapping means a new index and a reindex job, never an in-place edit.
- Purging a Tenant is deleting one index.
- Cross-Tenant search is impossible by construction, which is intended.
