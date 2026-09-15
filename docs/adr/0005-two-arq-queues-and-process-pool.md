---
status: accepted
date: 2026-09-14
---

# Two arq queues, two worker services, CPU work in a process pool

Background work runs on arq over Redis with two named queues: `ingest` (PDF extraction, OCR, chunking, embedding, indexing) and `tasks` (purges, Grace Period emails, backups, eval export, cron). Compose runs two worker services from the same image: `worker-ingest` with a low `max_jobs` and a `ProcessPoolExecutor` for CPU-bound steps, and `worker-tasks` with a higher `max_jobs` and no pool. The arq `job_id` for Ingestion is the Document id, so duplicate enqueues collapse and each step checks the Document's current state before acting.

Why: arq runs jobs as coroutines on one event loop, so a CPU-bound step such as rasterising or OCR-ing a page blocks every other job in that process, including the heartbeat. Offloading CPU steps to a process pool keeps the loop free, and separating queues keeps a 200-page scan from delaying an email or a purge, since arq has no job priorities. An in-process `asyncio.Queue` was considered and rejected as a job queue: it is not durable, not shared across processes, and empties on restart.

## Consequences

- Scaling ingestion is `docker compose up --scale worker-ingest=N`; scaling never changes code.
- Calls to the embedding API are throttled by a Redis token bucket keyed on model id, because a per-process semaphore stops working at two replicas.
- A per-Tenant fairness queue is a later change; with one Tenant it is not needed.
