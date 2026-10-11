# Kith MVP design

Outcome of the design interview held 2026-09-14. Vocabulary is defined in `CONTEXT.md`; hard-to-reverse choices are in `docs/adr/`; vendor comparisons with sources are in `docs/research/`. This file is the settled shape of the MVP. Anything not listed here was not decided.

## 1. Product

- A team of 1 to 50 people uploads PDFs into a shared pool and searches them. Search returns Filename Search matches, Retrieval (ranked Chunks with highlights, grouped by Document), and on demand an Answer with Citations. No chat, no Tags, no filters in the MVP.
- One Tenant exists today; everything carries `tenant_id` so a second is a data change. "Workspace" is the UI word only.
- Single VPS with docker-compose. A move to AWS later is a config change: S3-compatible storage, OTLP-only telemetry, provider interfaces everywhere.

## 2. Identity and tenancy

- FastAPI owns sign-in: Google OAuth via `authlib`, and magic links as single-use tokens hashed in Redis with a 15-minute TTL. Sessions are opaque ids in Redis, 30 days sliding, rotated on login, in an httpOnly SameSite cookie on the parent domain shared by the `app.` and `api.` hosts. Next.js holds no identity state: a project-root edge layer (not yet implemented) will check the cookie and call `GET /me`. Users, Profiles and OAuth account links live only in Postgres. See ADR-0006 (supersedes ADR-0003).
- First sign-in is signup; it creates the User and Profile and activates any Pending Membership for that email. The browser calls FastAPI directly with the session cookie; the API checks the Origin header on state-changing requests. Magic-link requests return the same response whether or not the email exists.
- A User with no active Tenant Membership sees onboarding: create a Tenant (name; slug derived) and become its Owner, or wait to be added. A User may create one Tenant. A User may hold memberships in several Tenants; the switcher picks one; URLs are `/w/{slug}`.
- Members are added directly by email (Pending Membership, no token, no expiry, revocable). Default Role is `member`; Role is stored so it can change.
- Roles and permissions:

| Action | Owner | Admin | Member | Viewer |
|---|---|---|---|---|
| Search, Retrieval, read and download Documents | yes | yes | yes | yes |
| Ask | yes | yes | yes | no |
| Upload, rename own Document | yes | yes | yes | no |
| Delete any Document | yes | yes | no | no |
| Add/remove members, change Roles (below Admin) | yes | yes | no | no |
| Settings | yes | yes | no | no |
| Promote/demote Admin | yes | no | no | no |
| Delete Tenant, transfer ownership, change slug | yes | no | no | no |

- The Tenant row carries `owner_id`. The Owner cannot leave without transferring ownership. Slug changes have no redirect.
- Tenant deletion: soft delete, 14-day Grace Period during which the Owner can restore, reminder emails at 7 days and 1 day before purge, then a worker job purges index, S3 prefix and rows.
- Account deletion: memberships, Profile, Queries, Asks and Feedback are deleted, and the User's Documents are deleted with them (product decision; GDPR would not require deleting shared Documents). Deleted rows persist in Postgres backups for 30 days; the retention notes must say so.
- Audit Log records membership, Role, settings, ownership and Document-deletion changes. Admins and the Owner can see all Queries and Asks in the Tenant; the UI says so.

## 3. Documents and Ingestion

- PDF only. Per-file limit 20 MB (env; higher in dev). Page cap 100 (env; raise once a large Document has been ingested and timed), checked at finalize before the Document exists. The stored PDF is never compressed.
- Upload: direct to S3 with a server finalize, see ADR-0009. `POST /uploads/init` sends `{filename, size, sha256, content_type}`, so a known duplicate is refused before bytes move, and returns a presigned PUT to `pending/{tenant_id}/{upload_id}`. `POST /uploads/{id}/finalize` downloads the object, computes the SHA-256 itself, rejects encrypted, unreadable or over-cap PDFs with a 422, copies it to `tenants/{tenant_id}/documents/{document_id}.pdf`, and creates the Document. Duplicate returns a conflict naming the existing Document and its Uploader. Hash mismatch is rejected as corrupt. The web client queues files two at a time; a folder drop is flattened and non-PDFs are skipped with a visible note.
- Storage: S3-compatible via MinIO behind the storage-provider interface copied from business-os. The PDF is the source of truth. Downloads and the viewer use short-lived presigned URLs; MinIO therefore needs a public host behind the reverse proxy.
- Extraction (see `docs/research/pdf-text-extraction-choice.md`): `pypdfium2` reads text-layer pages with character positions and rasterises pages. A per-page heuristic (fewer than ~20 non-whitespace characters or many replacement characters, with image area over half the page) flags scanned pages. Flagged pages pass a raster quality gate: 200 DPI grayscale (env), blank-page skip, contrast normalisation, quality flags stored per page and surfaced as a Document warning. Flagged pages go to the `OcrProvider`, Azure AI Document Intelligence Read by default, Tesseract as the optional local implementation. No vision-LLM step. OCR runs per flagged page with no separate cap; the page cap bounds its cost and time.
- Page text is stored in Postgres `document_pages` (page, text, source, confidence, render DPI, quality flags). See ADR-0002.
- Chunking: page-bounded token windows, ~500 tokens with 50 overlap (env), splitting on paragraph boundaries when possible; chunking parameters versioned on the Document. Chunks carry page number and character offsets; Citations are page-level in the MVP.
- Embedding: Voyage `voyage-4-large`, 1024 dimensions, batched by token count, throttled by a Redis token bucket. See ADR-0004.
- Index: one shared OpenSearch index with `tenant_id` on every Chunk, `knn_vector` 1024 `cosinesimil` HNSW Faiss, `text` field for BM25 with fuzziness, plus `tenant_id`, `document_id`, `page_number` and a `deleted` flag. OpenSearch 2.19+. Index name, alias, field list and isolation are in ADR-0012.
- Ingestion Status: `uploaded → processing → partial | ready | failed`, plus `deleted`; derived from Chunk statuses. Transient errors (including 429) retry three times with backoff; deterministic errors fail at once. Admins can retry, and a retry re-runs only failed Chunks. Reasons are shown in human phrasing; raw exceptions only in logs. While `processing`, the Document also carries an Ingestion Stage (`extracting`, `chunking`, `embedding`, `indexing`) updated by the worker between steps, and page progress (pages extracted of page count) during extraction. The UI polls; `GET /documents/summary` returns `{in_progress, failed}` for the Uploads banner. Retry is offered only for transient failures.
- Deletion: soft delete flips the Document to `deleted` immediately and flags its Chunks `deleted` in the index (excluded from search), a worker job purges Chunks and the file. Deleting during `processing` sets a flag the worker checks between steps. Uploader, Admin or Owner may delete.
- Worker: arq, two queues (`ingest`, `tasks`), two services, process pool for CPU steps, `job_id` = Document id. See ADR-0005. The Ingestion job payload is `document_id` and `tenant_id` only; the worker reads the storage key and state from Postgres and downloads the PDF itself. The API enqueues after the finalize commit, and a `tasks` cron re-enqueues Documents stuck in `uploaded` and expires stale Uploads (ADR-0009).

## 4. Search and Asks

- One search box on the dashboard (`/w/{slug}?q=…&type=search`), no keyword/semantic toggle. `POST /search` returns Retrieval only: hybrid BM25 + kNN on the Query's `voyage-4-large` embedding with reciprocal rank fusion, filtered by `tenant_id` and not-`deleted`, ~30 fetched, deleted Documents also dropped in Postgres, top 20 returned as one flat list (ADR-0015). Search is never reranked. Ask's Retrieval fetches 50, drops deleted Documents, reranks with `rerank-3` and keeps the top 5 (env: `RERANK_ENABLED`, `RERANK_MODEL`, `RERANK_FETCH_SIZE`, `RERANK_RESULT_LIMIT`); if Rerank is off or fails, the top 5 in RRF order (ADR-0015 amendment). Ask reconciles those 5 with `ANSWER_CONTEXT_N` when it is built. Highlights from the BM25 highlighter; kNN-only hits show the Chunk start. Embedding down: keyword leg only, flagged `degraded` ("Showing keyword matches only"). Results cached in the browser for 5 minutes per Tenant + Query, cleared on upload or delete.
- Filename Search is not part of `/search`: it filters the already-loaded Document list on the Uploads page in the browser, and moves to the server once the 20-Document Limit is lifted.
- `POST /asks` is on demand, streamed over SSE: a Citations event first, then Answer tokens. The Answer uses `ANSWER_CONTEXT_N=3` Chunks. Caps: 1,024 output tokens, 8,000 input tokens, 60-second timeout (env). The Answer model is behind `AnswerProvider`; model tier is a config table `{fast, quality}`, chosen by env in the MVP. Answer language matches the Query; strictness is `strict` (only what the Citations say, else "not found"). The three preference values are stored on the Tenant with defaults; there is no settings page for them yet.
- Prompt injection: Chunks are wrapped in delimited data blocks with a system instruction to treat them as untrusted, the Answer model has no tools, and the eval asserts injected instructions are not followed. No user-facing flagging.
- Answer model down: the Ask fails with a clear message, Retrieval results still show, the Ask is not counted.
- Query Log stores Query, User, retrieved Chunk ids with scores, the Answer if any, and Feedback (thumbs plus optional 500-character comment). Asks persist and are reopenable. Trimmed after 90 days. Recent searches are per User. Deferred: not built with Search; the Query Log, its 90-day trim and recent searches come with Ask.
- Query embedding cost is negligible; Retrieval is never blocked by Limits.

## 5. Usage, Limits, rate limits

- Usage per Tenant: Documents, storage bytes, Asks, Answer tokens (input + output as reported by the provider). Embedding and Rerank tokens are not Usage. The number of Asks is shown but limits nothing.
- Default Limits: 100 MB storage, 20 Documents. Both block. No payment.
- Asks are bounded by the Tenant's Credit Balance (ADR-0017): language-model tokens kept as an append-only Credit Ledger (`credit_ledger`) whose sum is the balance. It never resets. Rows are Ask Charges (each Ask's reported input + output tokens, naming its User) and Credit Adjustments (always with a note: the starting grant, an operator top-up via `make adjust-credits`, or a correction). Shown in Credits, 1 Credit = 1,000 tokens, rounded down. A Tenant created through onboarding starts with `STARTING_CREDIT_GRANT` (200) Credits; Tenants that existed before the ledger start at 0, with no backfill. An Ask may start while the balance is above 0, so concurrent Asks can leave it slightly negative. `GET /credit-balance` returns `{ credits, tokens, is_low, is_exhausted }` to Roles that may Ask; the sidebar shows "N credits left", amber below `CREDIT_LOW_THRESHOLD` (20) Credits, "No credits left" at or below 0. Hidden for Viewers.
- Rate limits in Redis (env): per User 60 searches/minute and 10 Asks/minute; per email 5 magic-link requests/hour. Upload starts are counted from the `uploads` table instead (env): per User 30 starts in the past hour and 5 pending Uploads younger than 30 minutes, so the retry hint is exact. The Documents and storage Limits are env defaults, the same for every Tenant, until Limits become per Tenant.

## 6. Surfaces

- API under `/api/v1`, Tenant scoped by header, RFC 9457 problem-details errors: `auth/google`, `auth/google/callback`, `auth/magic-link`, `auth/magic-link/verify`, `auth/logout`, `me`, `tenants`, `tenants/{id}/memberships`, `documents` (upload, list, get, rename, delete, download, retry), `search`, `asks`, `asks/{id}/feedback`, `usage`, `queries`.
- Pages: `/signin`, `/onboarding`, `/w/{slug}` (search + Ask), `/w/{slug}/documents`, `/w/{slug}/documents/{id}` (PDF viewer opened at a Citation's page; deferred: for now the same viewer component opens in a popup, at the passage's page from Search and at page 1 from Uploads, with page arrows and "Open full document" via a short-lived presigned download URL), `/w/{slug}/settings` (general, members, usage). Full desktop and mobile parity.
- Frontend: Next.js 16, React 19, Tailwind 4, shadcn/ui, TanStack Query over a client generated by `openapi-typescript` (CI checks it is current), `react-pdf`, `next-intl` with English-only copy.
- Backend: FastAPI, Pydantic v2, SQLAlchemy 2.0, `dependency-injector`, Alembic; domains `identity, tenancy, documents, ingestion, search, asks, usage, shared`. Storage provider, dedup hasher and cache provider adapted from business-os; rate limiting and observability re-implemented.
- Email: Resend behind a `Mailer` interface in FastAPI, which sends magic links, membership notices and Grace Period reminders; SMTP as the fallback implementation; Mailpit in compose. Next.js sends no email.

## 7. Infrastructure and operations

- `infra/docker-compose.yml`: `postgres` 16, `redis` 7, `opensearch` 2.19+ single node, `opensearch-dashboards`, `minio`, `mailpit`, `api`, `worker-ingest`, `worker-tasks`, `web`, `caddy`, `otel-collector`. Observability overlay adds `otel-lgtm` for dev. One `.env.example` at the root; a single root-owned `.env` on the VPS, no secrets manager.
- Toolchain: Python 3.12 with `uv`, Node 22 with pnpm 9 (bump from 8.6.12), MIT licence (verify business-os's licence before copying).
- Telemetry: OpenTelemetry SDKs only, exporting OTLP to the local Collector from env vars; the Collector config is the only place a vendor appears. Production starts on Grafana Cloud Free; OpenObserve is the self-hosted fallback (`docs/research/observability-backend-choice.md`). Sentry for errors in API, worker and web, confined to one init file each. No PostHog; a no-op `analytics.track` module reserves the seam. Logs and traces carry ids only, never Query text or emails.
- Deploy: GitHub Actions builds images on merge to `master`, filtered by path (`frontend/`, `backend/`), pushes to GHCR, SSHes to the VPS for `compose pull && up -d`; migrations run as a one-shot container before `api`. Two environments: local compose and prod.
- Backups: nightly `pg_dump` to a MinIO bucket, 30-day retention; VPS provider snapshot for the volume; OpenSearch not backed up (rebuildable). Off-site replication only on AWS.
- Reverse proxy: Caddy with automatic TLS in front of `web`, `api` and MinIO's presigned-URL host. Local development also runs behind Caddy on one hostname so the session cookie's parent-domain rule holds in dev exactly as in prod.
- Rate limit on magic-link requests (5/hour per email) doubles as the enumeration and spam guard for the login flow.

## 8. Quality

- Backend: pytest with real Postgres, Redis, OpenSearch and MinIO via testcontainers; providers mocked behind interfaces. Frontend: Vitest plus one Playwright flow (sign in, upload, search, ask) against compose. CI on GitHub Actions.
- Seed Tenant: 30 to 80 synthetic PDFs generated by `reportlab` from committed templated text, including image-only pages for OCR and pages with injected instructions. Golden Set `eval/golden.jsonl`, 40 to 60 entries covering paraphrase, exact identifier, typo, unanswerable and injection cases, English and French at minimum. Runner computes recall@6 and MRR; CI uses committed embedding fixtures keyed by model id and text hash; a manual or nightly job re-embeds with the real key.
- `kith eval candidates --since DATE` prints thumbs-down Asks and zero-result Queries as JSONL for manual review into the Golden Set.
- Before ADR-0004 is treated as final, run the Golden Set against Jina v5 as a second candidate.

## 9. Known gaps, deliberately deferred

- No malware scanning of uploads (ClamAV is one container when the door opens wider).
- Passage-level highlighting in the viewer (offsets are stored; UI work only).
- Tags, filters, chat, DOCX and other formats, per-Tenant queue fairness, AI preferences page, PostHog, French UI, off-site backups, vision-LLM OCR fallback.
- Azure Read pricing was confirmed only from secondary sources; verify on account creation.
