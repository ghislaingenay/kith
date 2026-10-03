---
status: accepted
date: 2026-10-03
---

# A reusable circuit breaker in `core`, applied to the search store by a `SearchIndex` wrapper

ADR-0011 says every call to the search store goes through the retry handler and an in-house circuit breaker. This records where each piece lives, and why the breaker is applied by a wrapper around the search-index interface instead of at each call site.

## Where the pieces live

- **`core/circuit_breaker/`** holds the breaker itself. It knows nothing about search: it takes a `name`, a failure threshold, a reset timeout, the exception types that count as failures, and a clock. Any other service (mail, storage, an embedding API) can use it by creating its own breaker. `CircuitOpenError` carries the breaker's name as `service`.
- **`core/search/circuit_breaker_index.py`** holds `CircuitBreakerSearchIndex`, a `SearchIndex` that sends each call through an injected breaker and then calls the real index. It is the only search-specific part.
- **`core/container.py`** builds one breaker named `search` per process and wraps the OpenSearch index with it. It also decides that only `SearchUnavailableError` counts as a failure. Settings are `CIRCUIT_BREAKER_FAILURE_THRESHOLD` (5) and `CIRCUIT_BREAKER_RESET_TIMEOUT_SECONDS` (30).
- **`OpenSearchIndex`** decides what counts as unavailable: no connection, a timeout, or a 429 or 5xx answer, including bulk items refused that way. A request the store rejects (a 400, a mapping conflict) would fail the same way again, so it raises a plain `SearchError`. It is neither retried nor counted, so one bad Document cannot open the breaker for every Tenant. Ingestion records such a batch as a Chunk Dead Letter at once, with one attempt, instead of raising, so the queue does not re-run the job on a request that will fail the same way each time.

## How the breaker behaves

Closed, it passes calls through and counts consecutive failures. The fifth opens it. Open, calls fail at once with `CircuitOpenError` and never reach the store. After the reset timeout, one call (the probe) is let through; a success closes the breaker and a failure opens it again for another timeout. Other calls arriving while the probe runs are rejected.

A call remembers the state it started in. A slow call that began while closed and ends after the breaker opened is stale: it can neither close the breaker nor stand in for the probe. An error that is not a store failure (a bug, a cancellation) neither counts nor closes the breaker, and a probe that dies of one reopens it with a fresh timeout, so it is never stuck half open. Every state change and every rejected call is logged with the breaker's name.

The retry handler wraps the breaker call and retries only `SearchUnavailableError`. `CircuitOpenError` is a different type, so a rejected call is not retried. That is what makes it fail fast.

## Why a wrapper, not the call sites or the OpenSearch client

ADR-0012 makes `SearchIndex` the only code that talks to the search store. Putting the breaker there means:

- Callers (ingestion, `ChunkSearchService`) just call `search_index.index_chunks(...)`. None of them can forget the breaker, because there is no unguarded path to the store.
- One breaker is shared by every job and request in the process, so they all see the same state of the store.
- The breaker does not know about OpenSearch, and `OpenSearchIndex` does not know about the breaker. Tests put the real breaker, on a fake clock, around a scripted fake index.

Alternatives we rejected: calling `breaker.call(...)` around each search call in `ingest.py` and the search service (it leaks the breaker into domain code and relies on every new caller remembering it); and building the breaker into `OpenSearchIndex` (it ties the breaker to one implementation and makes the failure behaviour hard to test with a fake).

## Consequences

- The wrapper forwards `alias`, `ensure_index`, `alias_exists` and `close` unchanged. That is boilerplate we accept, and a reviewer may flag it as a middle man. `ensure_index` and `alias_exists` are deliberately not guarded: they run at startup and from the create-index script, where failing fast on a dead store is the right behaviour without a breaker.
- Adding a method to `SearchIndex` means adding it to the wrapper too, and deciding whether it goes through the breaker.
- The breaker's state is per process, so the API and the ingest worker each keep their own. A store that is down opens each one separately.
- Guarding `search_chunks` goes beyond ADR-0011, which scopes the breaker to bulk indexing. It was kept because the issue asks for the breaker to wrap each search call.
