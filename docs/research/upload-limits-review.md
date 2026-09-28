# Upload/document limits: are they right for this stage?

Context: kith's document upload flow is direct-to-S3 with server finalize
(ADR-0009): `POST /uploads/init` validates and returns a presigned PUT, the
browser PUTs to S3, `POST /uploads/{id}/finalize` re-downloads and
re-validates the object server-side before it becomes a Document. All limits
are env-configured on `UploadSettings` (`backend/app/documents/config.py`)
and are the same for every Tenant; `Tenant.tier` (free/professional/
enterprise) exists but is not read by any limit check.

Sources below are primary (AWS S3 and AWS Prescriptive Guidance docs, OWASP
Cheat Sheet Series, AWS Well-Architected SaaS Lens, Stripe's own API docs,
Cloudflare's own engineering blog) and were fetched on **2026-09-27**.

## 1. Current state

| Limit | Value | Enforced in | File:line |
|---|---|---|---|
| Max file size | 20 MB (`UPLOAD_MAX_FILE_BYTES`) | `init_upload`, declared-size check | `backend/app/documents/config.py:12-14`; `backend/app/documents/service.py:62-64` |
| Max pages per PDF | 100 (`UPLOAD_MAX_PAGES`) | `_validate_and_promote`, after real parse with pypdfium2 | `config.py:18`; `service.py:219-225` |
| Max documents per tenant | 20 (`UPLOAD_MAX_DOCUMENTS`), flat for every tier | `_check_limits`, called at `init` and again inside finalize | `config.py:19-20` (docstring: "same for every Tenant until Limits are per Tenant"); `service.py:171-178`, called from `service.py:77` and `service.py:233` |
| Max storage per tenant | 100 MB (`UPLOAD_MAX_STORAGE_BYTES`), flat for every tier | `_check_limits`, same two call sites as above | `config.py:21-23`; `service.py:179-184` |
| Max upload starts per user | 30/hour (`UPLOAD_MAX_STARTS_PER_HOUR`), DB-counted | `_check_user_may_start`, counts rows via `repository.upload_start_times_since` | `config.py:27-29`; `service.py:129-158`; `backend/app/documents/repository.py:170` |
| Max concurrent pending uploads per user | 5 (`UPLOAD_MAX_PENDING_PER_USER`) | same method, counts non-expired pending rows via `repository.count_pending_uploads_since` | `config.py:24-26`; `service.py:160-169`; `repository.py:157` |
| Presigned URL TTL | 10 min (`UPLOAD_PRESIGNED_URL_TTL_SECONDS`) | `generate_presigned_put` call in `init_upload` | `config.py:15-17`; `service.py:87-93` |
| Pending upload expiry | 30 min (`UPLOAD_PENDING_EXPIRY_SECONDS`) | frees a concurrent-pending slot in `_check_user_may_start`; also the cron sweep described in ADR-0009 that expires stale pending rows and deletes their S3 objects (that cron is not in `service.py`) | `config.py:30-32`; `service.py:161-163` |

Violations surface as domain exceptions (`backend/app/documents/exceptions.py`)
mapped to HTTP by `register_document_exception_handlers`
(`backend/app/documents/exception_handlers.py:21-68`): `LimitReachedError` and
`DuplicateDocumentError` → 409, `TooManyPendingUploadsError` and
`UploadRateExceededError` → 429 (`UploadRateExceededError` also carries a
`Retry-After` header, `exception_handlers.py:43-56`), `TooManyPagesError`
(a `RefusedUploadError`) → 422.

**Tier confirmed unused.** `Tenant.tier` is a `CHECK`-constrained column
(`backend/app/tenants/models.py:44-49`) set only to a default at tenant
creation (`backend/app/tenants/repository.py:207,243`); no document/upload
limit reads it. `config.py:19-20`'s own docstring says as much for
`max_documents`, and it applies equally to `max_storage_bytes`.

ADR-0009 (`docs/adr/0009-direct-to-s3-uploads-with-server-finalize.md`)
records the one piece of limit history that exists: the per-user cap was
"10 uploads/hour" via Redis, replaced by 30 starts/hour + 5 concurrent
pending, **both counted from the `uploads` table rather than Redis**, because
"a refused start does not count and the retry hint is exact" and "the old
limit would block a legitimate 15-file batch." No other ADR in `docs/adr/`
(0001–0008) touches tiering or rate limiting; ADR-0001 puts one OpenSearch
index per tenant and ADR-0004 picks the embedding/reranker models, both of
which mean each accepted Document has a real per-tenant ingestion cost behind
it, not just S3 storage.

## 2. Best practices (primary sources)

**Direct-to-S3 / presigned URLs**
- AWS S3 presigned URLs default to a console max of 12 hours and an
  SDK/CLI max of 7 days; S3 checks expiry only at request time, and a
  presigned URL is a bearer token, so AWS recommends limiting its
  capabilities. ([Download and upload objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html))
- AWS's own worked example for the `s3:signatureAge` guardrail — a policy
  that denies presigned requests once the signature is older than a set
  age — uses **15 minutes** as the illustrative ceiling, "to limit validity
  to a similar timeframe as standard signing supports," and separately notes
  it isn't practical to go below ~60 seconds. ([Additional guardrails — AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/presigned-url-best-practices/additional-guardrails.html))
- A single `PutObject` supports up to 5 GB; AWS recommends multipart upload
  once an object reaches 100 MB, with multipart parts from 5 MiB to 5 GiB.
  ([Amazon S3 multipart upload limits](https://docs.aws.amazon.com/AmazonS3/latest/userguide/qfacts.html); [Uploading and copying objects using multipart upload](https://docs.aws.amazon.com/AmazonS3/latest/userguide/mpuoverview.html))
- OWASP: never trust client-declared `Content-Type` or size — "it is
  trivial to spoof" — validate server-side; set size limits to protect
  storage capacity; conduct all validation before any action is taken on an
  uploaded file. ([OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html))

**Multi-tenant SaaS quota design**
- AWS Well-Architected SaaS Lens: introduce throttling/quotas so "no single
  tenant can put load on the system in a way that impacts... other
  tenants," and make quotas tier-aware by defining an SLA and a request
  volume "for each tier" — i.e., tiering is a plan-differentiation
  mechanism (API Gateway usage plans per tenant tier), not a default you
  need before you have paying tiers. ([How do you limit an individual tenant's ability to impose load — SaaS Lens](https://wa.aws.amazon.com/saas.question.REL_1.en.html))
- Stripe's own rate limits are global-account limits (100 req/s live,
  25 req/s per endpoint) plus a handful of resource-specific limits, not
  something a customer configures per plan; Stripe separates rate limits
  from concurrency limits and tells integrators to self-throttle with a
  client-side token bucket. ([Stripe: Rate limits](https://docs.stripe.com/rate-limits))

**Rate-limiting algorithm tradeoffs**
- Cloudflare's own engineering blog describes the sliding-window-counter
  approximation it built at scale — blending the previous and current fixed
  window's counts — because storing exact timestamps for millions of keys
  doesn't scale; the tradeoff is a small (~6% in their measurement),
  bounded error in exchange for O(1) state per key. kith already has this
  exact pattern in `backend/app/core/ratelimit/limiter.py`
  (`SlidingWindowLimiter`, explicitly "Cloudflare-style" in its docstring)
  for other rate limits, and a simpler `CounterLimiter`
  (`backend/app/core/ratelimit/counter_limiter.py:14-27`) whose own
  docstring says it is "not... a fit for anything that must be exact under
  contention." ([Cloudflare: How we built rate limiting capable of scaling to millions of domains](https://blog.cloudflare.com/counting-things-a-lot-of-different-things/))
- ADR-0009's own reasoning for choosing DB-counted over Redis-counted for
  upload starts matches this tradeoff exactly: Redis/sliding-window
  approximations are the right tool when the limit is generous and
  approximate is fine (kith's own `CounterLimiter` docstring gives "an
  email-send rate limit" as its example); exact DB counting is the right
  tool when a refused attempt must not consume budget and the retry-after
  must be exact — which is what upload starts need, per ADR-0009.

## 3. Recommendations

- Max file size (20 MB): KEEP — well under S3's 5 GB single-`PutObject` ceiling and its 100 MB multipart-recommendation threshold (AWS S3 multipart upload limits doc), so it isn't forcing multipart complexity, and it bounds the worst case of the OWASP-recommended size limit.
- Max pages per PDF (100): KEEP — re-derived from the real file with pypdfium2 at finalize rather than trusted from the client (`service.py:219-225`), which is exactly OWASP's "don't trust client-declared metadata, validate before acting on it" principle.
- Max documents per tenant (20, flat across tiers): DEFER — `Tenant.tier` exists (`tenants/models.py:44-49`) but is never read for quotas (`tenants/repository.py:207,243` only sets the default); per the AWS SaaS Lens, tier-based quotas should track a monetized plan difference, so a single default is correct until tiers are actually sold.
- Max storage per tenant (100 MB, flat across tiers): DEFER — same tier-unused gap as document count; it currently functions as a cost guard on the per-tenant OpenSearch index (ADR-0001) and embedding calls (ADR-0004) behind each Document, which is a real cost to bound pre-monetization, so keep the flat default rather than inventing a tier split with no pricing behind it yet.
- Max upload starts per user (30/hour, DB-counted): KEEP — ADR-0009 already made this trade-off deliberately (moved off Redis specifically so a refused start doesn't count and the retry hint is exact), matching the documented distinction in kith's own `CounterLimiter` (approximate is fine for generous budgets) versus this limit's need for exactness.
- Max concurrent pending uploads per user (5): KEEP — a small bound against abandoned uploads accumulating in the `pending/` S3 prefix and the `uploads` table, and ADR-0009 explains the number was chosen so it doesn't block a legitimate multi-file batch.
- Presigned URL TTL (10 min): KEEP — tighter than AWS's own illustrative `s3:signatureAge` guardrail ceiling of 15 minutes ("to limit validity to a similar timeframe as standard signing supports"), and nowhere near the 7-day SDK maximum, i.e. already at the conservative end AWS itself demonstrates.
- Pending upload expiry (30 min): KEEP — gives 3x the presigned URL's TTL as buffer for retries before a slot is reclaimed (`service.py:161-163`), and is what caps how long a stalled upload can occupy one of the 5 concurrent-pending slots.
