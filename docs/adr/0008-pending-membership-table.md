---
status: accepted
date: 2026-09-17
amended: 2026-09-20
---

# Pending Membership is its own Postgres table, not Redis or a new datastore

`tenant_memberships.user_id` is `NOT NULL`, so an email added to a Tenant before it has signed in has nowhere to live in that table. We add a dedicated `pending_memberships` table in the existing Postgres. On that email's first sign-in each live row is converted into a real `TenantMembership` and **kept as history**, closed with status `accepted`.

Why Postgres: Redis (already used for sessions and magic links) would lose a Pending Membership on eviction or restart, and we want the row to outlive its use as a record of who was added and when. MongoDB's TTL indexes would solve durability but introduce a second database for one small table. Postgres is already the system of record for Users and Tenants, needs no new infrastructure, and gives the row the same durability guarantees as everything else membership-related.

> Amended 2026-09-20. The first version said the row has "no TTL" and is deleted on first sign-in. Both changed after comparing how GitHub, WorkOS and Auth0 handle invitations; the evidence and open questions are in `docs/research/pending-membership-invitation-practices.md`. Where a rule below rests on our own judgement rather than a vendor's documented behaviour, it says so.

## Schema

`pending_memberships`: `id` (surrogate key), `tenant_id`, `email`, `role`, `status`, `invited_by`, `created_at`, `accepted_at`, `accepted_by_user_id`.

- **Surrogate `id`, not a `(tenant_id, email)` key.** A composite key allows one row per tenant and email forever, which makes history impossible. The only uniqueness rule is a partial unique index, `UNIQUE (tenant_id, email) WHERE status = 'pending'`: at most one live row per Tenant and email. A key on `(tenant_id, email, status)` was rejected because it allows only one row per status, so a second `accepted` or `expired` row would fail.
- **`email` is stored trimmed and lowercased**, enforced by `CHECK (email = lower(btrim(email)))` so no code path can create `Alice@x.com` beside `alice@x.com`. `+tag` is not stripped. The app normalises the same way before writing or matching `users.email` on the magic-link path.
- **`accepted_at` and `accepted_by_user_id`** record when and by whom a row was accepted; an accepted row without them is just a flag. `accepted_by_user_id` is `ON DELETE SET NULL`, like `invited_by`.

## Lifecycle

`pending` → `accepted` (the email signed in), `revoked` (an Admin withdrew it), or `expired` (aged out).

- `rejected` is not a status. Activation on sign-in accepts every live row, so nothing would ever set it. If a Member-facing "decline" is ever built, it is added then.
- `revoked` is set by an Admin action that does not exist yet (see follow-ups).

## Expiry

A Pending Membership is activatable for **7 days** from `created_at` (GitHub's invitations expire after 7 days; Auth0's default is 7). Our threat model differs from a vendor's, since the risk is stale Admin intent rather than a leaked link, so a longer or unbounded TTL would also be defensible; 7 days is the chosen default.

Expiry is applied **at match time** from `created_at`, in the query, never read from the stored `status`. A stored `expired` can be stale, so it is bookkeeping, not the source of truth. A row past its TTL still occupies the partial unique index until something closes it, so whatever code re-adds an email must mark the stale row `expired` in the same transaction as inserting the new `pending` row.

## Activation

On a verified magic-link sign-in (`GET /auth/magic-link/verify`), after the User is created or found:

1. List the live Pending Memberships for the normalised email.
2. Activate **all** of them, each identified by its own `tenant_id`, in **one transaction**, so a failure cannot leave the email half-activated. No "earliest" or other single row is selected. Vendors document per-invitation acceptance (WorkOS: a user joins only the organization whose invitation they clicked), so activating every match is our decision, made because there is no token to tell the rows apart.
3. Per row: `UPDATE ... SET status = 'accepted', accepted_at, accepted_by_user_id WHERE status = 'pending' AND created_at > now() - 7 days`, then `INSERT INTO tenant_memberships ... ON CONFLICT (tenant_id, user_id) DO NOTHING`.

Both statements are safe to repeat. On a retry, a double-click, or a concurrent sign-in the guarded `UPDATE` matches zero rows and the insert conflicts; both are treated as success. An already-existing membership is not an error.

Which Tenant the person lands in afterwards is not an activation decision. `GET /me` lists memberships ordered by `(created_at, tenant_id)` and the frontend redirects to the first. Rows activated together share a `created_at`, so `tenant_id` breaks the tie and the landing Tenant is stable. The Tenant switcher is out of scope for now.

## Security

- Activation happens only inside the magic-link verify path, where the single-use token has just proved the person controls the email. Nothing else activates a Pending Membership. Any future path (for example Google sign-in) must require a provider-asserted verified email, never an unverified form field or claim.
- Matching a Pending Membership needs no token in the link, so creating one must not reveal whether an email has an account. The magic-link request endpoint already returns the same response whether or not the email is known and never consults `pending_memberships`; it must stay that way, including response time.

## Consequences and follow-ups

- The row surviving activation costs a little storage and gives an audit trail of who was added and who accepted.
- Decided for now: Pending Memberships **survive** the removal of the Admin who created them (`invited_by` becomes null through `ON DELETE SET NULL`). Whether removing an Admin should revoke their pending rows is revisited when Admin removal exists.
- Not built yet: creating a Pending Membership (no UI or endpoint; tests seed rows directly), revoking one, marking stale rows `expired` on re-add, and enforcing normalised emails on `users.email` in the database. These are tracked in a follow-up issue.
- Unverified in a primary source (see the research note): whether a newer magic link invalidates the previous one, whether any vendor matches a passwordless sign-in to an invitation with no token, and lazy versus scheduled expiry.
