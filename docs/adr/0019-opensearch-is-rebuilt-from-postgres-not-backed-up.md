---
status: accepted
date: 2026-10-20
---

# OpenSearch is not backed up; it is rebuilt from Postgres

Postgres is backed up nightly (`pg_dump` to S3, kept 14 days). OpenSearch is not. Its Chunk text and metadata are copies of Postgres rows (ADR-0002), so only the embeddings exist nowhere else, and getting them back means paying Voyage again: about 3M tokens for the seed corpus, well under $1 and a few minutes. Recovery is `make rebuild-index`, which creates the index again, resets the Chunks' indexing and embedding statuses, re-indexes from Postgres and enqueues embedding through the existing jobs (ADR-0014). The same command fills a fresh OpenSearch Service index on the move to AWS, and handles any mapping or model change `make refresh-index` cannot. Keeping vectors in `_source` (ADR-0012) makes a reindex inside a running cluster free, but does not survive losing the cluster.

## Considered options

- **OpenSearch snapshots to S3.** Rejected: it needs a custom image with the `repository-s3` plugin, credentials in its keystore, and a second restore drill to keep working, all to save less than a dollar.
- **Store the vectors in Postgres too.** Rejected: it changes the schema and the embedding job, and adds about 4 KB per Chunk to the database and to every dump, for the same saving.

## Consequences

- After a loss, a Document comes back in keyword results once it is re-indexed, and in full hybrid results once its embedding catches up.
- A rebuild needs a working Voyage key with enough quota.
- Revisit when re-embedding the corpus costs real money or takes hours; snapshots are the answer then.
