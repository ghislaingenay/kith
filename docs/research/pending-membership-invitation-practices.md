# Pending Membership: how invitation flows are built elsewhere

Context: kith's Pending Membership (`pending_memberships`: tenant_id, email,
role, status in pending/accepted/rejected/expired, invited_by, created_at). An
Admin adds an email before that person has signed in; on the email's first
magic-link sign-in it becomes a Tenant Membership. There is no invite token:
the magic link proves control of the email and the row is matched by email.
Design under evaluation: on first sign-in activate ALL pending rows for the
email (each by its explicit tenant_id), keep the row and set status to
`accepted` instead of deleting it, and a 7-day expiry that is lazily marked
`expired`.

All sources below are primary (PostgreSQL 18 docs, RFC 5321, OWASP cheat
sheets, GitHub / WorkOS / Auth0 docs) and were fetched on **2026-09-20**. The
research was capped at 10 fetched pages, so several questions are thinly
sourced; those are marked _unverified_ or _unanswered_ rather than filled from
memory. Vendor docs use "invitation" and "workspace/organization"; this note
uses "Pending Membership" and "Tenant" in recommendations and "invitation"
only when describing or quoting a source. Note that the fetch tool returns
model-summarised extracts, so "the page does not say X" below means "X was not
in the extract", which is weaker than "X is not on the page".

## Summary

- Every vendor checked (GitHub, WorkOS, Auth0) ties acceptance to one specific
  invitation, sent to one email, and none documents an "activate all pending
  rows for this email" model. Activate-all is defensible for kith because there
  is no per-invitation click to disambiguate, but it is not established
  practice, and it makes the `rejected` status unreachable in the sign-in path.
- The intended uniqueness on `(tenant_id, email, status)` contradicts the goal
  of keeping history: it would forbid a second `accepted` (or `expired` or
  `rejected`) row for the same tenant and email. PostgreSQL's documented
  pattern is a partial unique index `WHERE status = 'pending'`.
- 7 days is the TTL of GitHub and the default of Auth0 (max 30 days). No
  source was found on lazy versus scheduled expiry.
- Magic-link sign-in plausibly satisfies "email verified": WorkOS states that
  accepting an invitation via the emailed link counts as email verification;
  GitHub requires a verified matching email on the accepting account.
- Idempotent accept: a single `INSERT ... ON CONFLICT` is atomic under
  concurrency per the PostgreSQL docs; use a partial-index conflict target and
  remember `RETURNING` does not return skipped rows.
- Two documents in the repo now disagree with the design: `CONTEXT.md` says
  Pending Membership has "no token and no expiry", and ADR-0008 says the row is
  "converted ... and deleted". Not modified here (research only).

## 1. Lifecycle and statuses; keep-and-deactivate versus delete

What sources say:

- GitHub: pending invitations can be cancelled or edited before acceptance;
  expired or failed invitations stay visible in a failed-invitations view with a
  "Retry invitation" action; for former members invited within the last three
  months the admin can "Invite and reinstate" prior privileges or start fresh.
  ([GitHub docs: Inviting users to join your organization](https://docs.github.com/en/organizations/managing-membership-in-your-organization/inviting-users-to-join-your-organization)).
  This implies expired rows are retained rather than deleted, but the page does
  not state a retention policy.
- WorkOS: the AuthKit invitations page mentions invitations can be "revoked"
  and speaks of "pending" invitations, but does not list a status enumeration
  in the extract read
  ([WorkOS: AuthKit invitations](https://workos.com/docs/authkit/invitations)).
  A full status list (pending/accepted/expired/revoked) is _unverified_; the
  API reference page was not fetched.
- Auth0: the page read covers sending invitations and the `ttl_sec` setting; it
  says nothing about lifecycle states, revocation or expiry behaviour
  ([Auth0: Send membership invitations](https://auth0.com/docs/manage-users/organizations/configure-organizations/send-membership-invitations)).
- Slack, Atlassian, Clerk, Microsoft Entra, Google Workspace: not read (see
  Unverified / open). Whether any vendor keeps accepted invitations as history
  rows is _unverified_.

Where they disagree: nothing checked contradicts anything else; the evidence is
just thin. No fetched source states "delete on accept" or "keep on accept".

Recommendation for kith:

- Keep-and-deactivate (status `accepted`) is consistent with what GitHub shows
  for expired/failed invitations (retained, retryable). It also gives Admins a
  "who invited whom and when" record. If that history is not wanted, note that
  the Audit Log (`CONTEXT.md`: "memberships added or removed") could carry it and
  the pending row could still be deleted; this is a design choice, not one
  dictated by sources.
- Add `accepted_at` (or `resolved_at`) and, if kept, `accepted_by_user_id`, so
  an `accepted` row is not just a flag. This is a suggestion; no source
  prescribes columns.
- Add a `revoked` status (or delete on revoke). The current set
  pending/accepted/rejected/expired has no value for "Admin withdrew it", and
  GitHub and WorkOS both document cancellation/revocation.
- `rejected` implies the invitee declines. In the design, sign-in activates all
  rows automatically, so nothing ever sets `rejected` in that path. Either
  drop `rejected`, or define who sets it (for example an Admin-side rejection)
  before shipping it. No fetched source documents a "declined" state
  (_unverified_).

## 2. Expiry: TTLs, whether to expire, lazy versus scheduled

What sources say:

| Product                 | TTL                                                                                                                                                         | Source                                                                                                                                    |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| GitHub                  | 7 days: "If an invitee does not accept the invitation within seven days, the pending invitation expires automatically." Expired invitations can be retried. | [GitHub docs](https://docs.github.com/en/organizations/managing-membership-in-your-organization/inviting-users-to-join-your-organization) |
| Auth0 (Organizations)   | `ttl_sec`: "If unspecified or set to 0, defaults to 604800 seconds (7 days). Maximum of 2592000 seconds (30 days)."                                         | [Auth0 docs](https://auth0.com/docs/manage-users/organizations/configure-organizations/send-membership-invitations)                       |
| WorkOS                  | Not stated in the extract read (_unverified_).                                                                                                              | [WorkOS docs](https://workos.com/docs/authkit/invitations)                                                                                |
| Slack, Atlassian, Clerk | Not read (_unverified_).                                                                                                                                    | n/a                                                                                                                                       |

- Whether to expire at all: GitHub and Auth0 both expire by default; no source
  discusses the case for non-expiring invitations.
- Lazy versus scheduled marking: _unanswered_. The vendor pages describe the
  behaviour ("expires automatically") but not the implementation.
- Note the difference in threat model: vendor invitations carry a bearer link,
  so the TTL bounds the window in which a leaked link is usable. kith has no
  invite token, so a TTL there only bounds how long an Admin's stale intent
  stays in force (an email added by mistake, or a person who changed roles).

Recommendation for kith:

- 7 days matches the two verified data points, but for a token-less Pending
  Membership the reason to expire is stale Admin intent, not link leakage, so a
  longer TTL (or none) is defensible. Whatever is chosen, `CONTEXT.md` and
  ADR-0008 currently say "no expiry", so they need to be reconciled with the
  code.
- Lazy expiry is safe only if the check happens at match time: on sign-in, treat
  a `pending` row past its TTL as expired (compare `created_at + interval`) and
  update it in the same statement; never rely on the stored `status` alone. A
  stored `expired` value that is written lazily can be stale, so queries that
  list pending rows must apply the same time predicate.
- Provide a re-add path: GitHub's "Retry invitation" corresponds to "Admin
  re-adds the email", which must create a fresh `pending` row (see section 3).

## 3. Uniqueness: composite key with status versus a partial unique index

What sources say:

- PostgreSQL documents the exact pattern: "create a unique index over a subset
  of a table ... This enforces uniqueness among the rows that satisfy the index
  predicate, without constraining those that do not." Example 11.3:
  `CREATE UNIQUE INDEX tests_success_constraint ON tests (subject, target) WHERE success;`
  which allows one "successful" entry per subject/target and any number of
  unsuccessful ones
  ([PostgreSQL 18: 11.8 Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html)).
- For `INSERT ... ON CONFLICT`, the `index_predicate` parameter is "used to allow
  inference of partial unique indexes", e.g.
  `ON CONFLICT (did) WHERE is_active DO NOTHING`
  ([PostgreSQL 18: INSERT](https://www.postgresql.org/docs/current/sql-insert.html)).
- Vendor behaviour for re-inviting after revoked/expired/accepted: GitHub
  documents retry after expiry and reinstatement of former members
  ([GitHub docs](https://docs.github.com/en/organizations/managing-membership-in-your-organization/inviting-users-to-join-your-organization)).
  Other vendors: _unverified_.

Recommendation for kith (contradicts the design as stated):

- A unique constraint on `(tenant_id, email, status)`, whether as composite PK
  or unique index, allows only one row per status value. So a second
  `accepted`, `expired` or `rejected` row for the same tenant and email is
  rejected by the database: invite, accept, member removed, re-invite, accept
  again would fail on the second `accepted`. That defeats keeping history.
- Use a partial unique index instead, which is the pattern PostgreSQL documents:

  ```sql
  CREATE UNIQUE INDEX pending_memberships_one_pending
      ON pending_memberships (tenant_id, email) WHERE status = 'pending';
  ```

  with a surrogate primary key (`id`) on the table. One `pending` row per
  tenant+email, any number of history rows.

- Re-adding after `expired`/`accepted`/`revoked`: insert a new `pending` row. The
  partial index blocks only a duplicate `pending`. Re-adding while one is still
  `pending`: use `ON CONFLICT (tenant_id, email) WHERE status = 'pending'` to
  either refresh `created_at`/`role` (renews the TTL, as GitHub's retry does) or
  return "already added".
- An expired row that is still stored as `pending` (lazy expiry) will block a
  re-add through the index until it is marked `expired`. Handle this by marking
  it expired in the same transaction before inserting, or by re-adding via the
  `ON CONFLICT ... DO UPDATE` path above.

## 4. Several pending rows for the same email across Tenants: activate all versus pick one

What sources say:

- WorkOS: users can "be invited to multiple organizations" and "they only join
  the organization for which they clicked the invitation email for"; for a
  new user they "automatically join the organization" on signup, and for an
  existing user, clicking the link and signing in "adds the user as a member to
  the organization"
  ([WorkOS](https://workos.com/docs/authkit/invitations)).
  That is per-invitation acceptance, the opposite of activate-all, and it
  depends on the click carrying an invitation code.
- GitHub: an email invitation is accepted by the invitee for that organization;
  the extract does not discuss several simultaneous invitations
  ([GitHub docs](https://docs.github.com/en/organizations/managing-membership-in-your-organization/inviting-users-to-join-your-organization)).
- Landing-tenant choice on sign-in (tenant picker, last-used, most recent):
  _unanswered_. Auth0's page read did not cover users with several
  organizations.

Where they disagree: there is nothing to reconcile; every fetched vendor flow is
per-invitation because it has an invite token or invitation code. kith
deliberately has none.

Recommendation for kith:

- Activate all is a reasonable consequence of the token-less design: each row
  was created by an Admin of that specific Tenant for that specific email, and
  the magic link is the only thing the invitee does. Each row is activated with
  its explicit `tenant_id`, which avoids the "which one is earliest" ambiguity
  and matches the repo's memory note that the service picks the rows and the
  repository takes the full key.
- Be aware that this differs from the per-invitation consent model of the
  vendors above: the user joins Tenants without choosing each. If that is
  acceptable, record each activation in the Audit Log, and give the User a way
  to leave a Tenant.
- Landing tenant: not sourced. A deterministic rule (for example the Tenant of
  the most recently created Pending Membership, or a picker when more than one
  activated) should be written down explicitly as a kith decision, not
  attributed to industry practice.
- Do the whole activation in one transaction so a User never ends up half
  activated (see section 7).

## 5. Email normalization and case-insensitive matching

What sources say (brief):

- RFC 5321 section 2.4: "The local-part of a mailbox MUST BE treated as case
  sensitive", but "exploiting the case sensitivity of mailbox local-parts
  impedes interoperability and is discouraged"; "Mailbox domains follow normal
  DNS rules and are hence not case sensitive"
  ([RFC 5321, section 2.4](https://www.rfc-editor.org/rfc/rfc5321#section-2.4)).
- PostgreSQL `citext`: comparison "internally calls `lower`"; it allows
  case-insensitive PRIMARY KEY and UNIQUE constraints; folding follows the
  database `LC_CTYPE`; "It is not truly case-insensitive in the terms defined
  by the Unicode standard"; it is less efficient than `text`
  ([PostgreSQL 18: citext](https://www.postgresql.org/docs/current/citext.html)).
- OWASP Authentication Cheat Sheet: no guidance on case handling of usernames
  or email addresses was found in the extract
  ([OWASP Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)).

Recommendation for kith:

- Treating the whole address case-insensitively is a deliberate departure from
  the RFC's letter, justified by the RFC's own "discouraged" note. Normalize
  (trim, lowercase) in the application on write to both `users.email` and
  `pending_memberships.email`, and additionally enforce it in the database so a
  missed code path cannot create `Alice@x.com` next to `alice@x.com`: either
  `citext` for both columns, or a `lower(email)` expression in the unique index.
  With `citext`, the partial unique index in section 3 is automatically
  case-insensitive; with `text` it must be an expression index and every
  lookup must use the same expression.
- Other normalization (Unicode, plus-addressing, provider-specific dot
  folding): _unverified_, no source read. Do not silently strip `+tag`.

## 6. Security of email-matched, token-less activation

What sources say:

- Email verification requirement. GitHub: the invitee "will only be able to
  accept the invitation if the email address matches with a verified email
  address associated with the invitee's personal account"
  ([GitHub docs](https://docs.github.com/en/organizations/managing-membership-in-your-organization/inviting-users-to-join-your-organization)).
  WorkOS: "Accepting an invitation shortly after it's sent counts as email
  verification" because the link goes to the invited address, and such users
  are marked `email_verified` and "are not sent a separate verification email";
  matching is on the invited email plus an invitation code, with a variation:
  consumer domains require an exact email match, corporate domains allow "any
  email address from the same domain as the email on the invitation"
  ([WorkOS](https://workos.com/docs/authkit/invitations)).
- Token in the link or not. In the fetched vendor pages, acceptance is tied to
  an invitation code or emailed link (WorkOS) or to an invitation the account's
  verified email matches (GitHub). Auth0 binds an invitation to an email
  address but the page read does not describe acceptance
  ([Auth0](https://auth0.com/docs/manage-users/organizations/configure-organizations/send-membership-invitations)).
  No fetched source describes a flow where a plain passwordless sign-in is
  matched to a stored invitation by email with no token at all (_unverified_
  whether any vendor does this).
- Enumeration. OWASP Authentication: "An application must respond (both HTTP
  and HTML) in a generic manner", and processing-time differences "allow an
  attacker to mount a time-based attack"
  ([OWASP Authentication](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html),
  section "Authentication and Error Messages"). OWASP Forgot Password: "Return a
  consistent message for both existent and non-existent accounts" and respond in
  a consistent amount of time, for example via asynchronous calls or "the same
  logic ... instead of using a quick exit method"
  ([OWASP Forgot Password](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html),
  section "Forgot Password Request").
- Single-use and token properties. OWASP Forgot Password, section "General
  Security Practices": reset identifiers must be generated with a
  cryptographically secure RNG, long enough to resist brute force, "Invalidated
  after they have been used", stored securely, and linked to an individual user.
  These are for password-reset tokens; magic links are analogous, not covered
  by that sheet.
- Rate limiting. OWASP Forgot Password: "protections against excessive automated
  submissions such as rate-limiting on a per-account basis, requiring a
  CAPTCHA, or other controls", otherwise an attacker could flood a victim's
  inbox.
- Newer link invalidating the previous one, and clicking an older or used
  link: not confirmed. The Forgot Password extract did not include either
  point (_unverified_), and the Clerk email-links page fetched returned only an
  index of SDK guides with no detail.

Recommendation for kith:

- Takeover risk of token-less matching: the design is only as safe as "the
  address holder is the person who gets the magic link". Therefore the
  Pending Membership must only be activated from a magic-link sign-in that
  verified the email (or from Google sign-in only if the provider asserts
  `email_verified` for that address; that requirement is a suggestion, no
  source read covers Google's claim). This mirrors GitHub's "verified email"
  condition and WorkOS's "accepting via the emailed link counts as
  verification". Never activate on the strength of an unverified email typed
  into a form or an unverified OAuth claim.
- Enumeration: the magic-link request endpoint must return the same response
  and roughly the same timing whether or not the email is a User or has a
  Pending Membership (OWASP). Do the "does a Pending Membership exist?" work
  only after the link is consumed, not when it is requested. The Admin
  "add member" endpoint necessarily reveals to an Admin whether an email
  already exists as a User if it answers differently; whether to accept that
  is a kith decision and no source read addresses it (_unanswered_).
- Magic links: single-use (consume atomically), short TTL, rate limit per
  email and per IP (OWASP). For "a newer link invalidates the previous one",
  no source verified; decide explicitly and test it.
- A stale row cannot be "used" the way a token can, but a former Admin's
  Pending Membership stays valid after that Admin is removed. Consider whether
  removing an Admin should cancel the pending rows they created (`invited_by`).
  Unsourced; a kith decision.

## 7. Idempotency on retried or concurrent sign-ins

What sources say:

- PostgreSQL INSERT: "ON CONFLICT DO UPDATE guarantees an atomic INSERT or
  UPDATE outcome; provided there is no independent error, one of those two
  outcomes is guaranteed, even under high concurrency." For `DO NOTHING` the
  conflict target is optional (all usable constraints and unique indexes are
  handled); for `DO UPDATE` it is mandatory. "Only rows that were successfully
  inserted or updated will be returned" by `RETURNING`, so rows skipped by
  `DO NOTHING` are absent from the result
  ([PostgreSQL 18: INSERT](https://www.postgresql.org/docs/current/sql-insert.html)).
- Row locking (`SELECT ... FOR UPDATE`, `FOR UPDATE SKIP LOCKED`), isolation
  levels and how a double-clicked verify request is best serialised: not
  fetched (_unverified_). The atomicity guarantee above is for one statement;
  the statement "one transaction covers all pending rows" is a design
  suggestion, not something the page states.
- Idempotent acceptance in vendor flows (retry of an accept call): _unanswered_.

Recommendation for kith:

- Make the TenantMembership insert idempotent with a unique
  `(tenant_id, user_id)` constraint and
  `INSERT ... ON CONFLICT (tenant_id, user_id) DO NOTHING`. If the User already
  has a membership (a retry, or two tabs), the insert is a no-op rather than an
  error. A concurrent second sign-in will either insert first or hit the
  conflict; both are correct.
- Mark the pending row accepted with a guarded update:
  `UPDATE pending_memberships SET status='accepted', accepted_at=now() WHERE tenant_id=:t AND email=:e AND status='pending'`.
  It matches zero rows on retry. Since `RETURNING` does not report skipped
  rows, the code must treat "zero rows" as success on retry, not as an error.
- Run the insert and the status update, for every pending row of the email, in
  a single transaction so a crash cannot leave a membership without the pending
  row being closed (or the reverse). Exact locking strategy: _unverified_, needs
  a look at PostgreSQL's explicit-locking docs.
- The magic-link token itself must be consumed atomically (single-use per
  OWASP), which is the outer idempotency guard: a second click on the same link
  fails at token consumption, and a second sign-in with a new link finds no
  `pending` rows left.

## Sources

Fetched 2026-09-20; ten pages, the cap.

1. PostgreSQL 18, 11.8 Partial Indexes: https://www.postgresql.org/docs/current/indexes-partial.html
2. PostgreSQL 18, INSERT (ON CONFLICT, RETURNING): https://www.postgresql.org/docs/current/sql-insert.html
3. PostgreSQL 18, citext: https://www.postgresql.org/docs/current/citext.html
4. RFC 5321, section 2.4 (case sensitivity): https://www.rfc-editor.org/rfc/rfc5321#section-2.4
5. WorkOS, AuthKit invitations: https://workos.com/docs/authkit/invitations
6. GitHub Docs, Inviting users to join your organization: https://docs.github.com/en/organizations/managing-membership-in-your-organization/inviting-users-to-join-your-organization
7. Auth0, Send membership invitations: https://auth0.com/docs/manage-users/organizations/configure-organizations/send-membership-invitations
8. OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
9. OWASP Forgot Password Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html
10. Clerk, email links custom flow: https://clerk.com/docs/guides/development/custom-flows/authentication/email-links (fetched, but the page returned only an index of SDK guides; nothing from it is cited above)

## Unverified / open

- Slack, Atlassian, Microsoft Entra, Google Workspace and Stripe were not read
  (source cap). Anything about their invitation lifecycles, TTLs (Slack's in
  particular) or decline behaviour is unverified.
- Clerk: the fetched page held no detail on link expiry, single use, or
  invitation tickets. Clerk's organization-invitation docs need a separate
  fetch.
- WorkOS: statuses and default expiry were not in the extract. The API
  reference for invitations is the likely place.
- Auth0: the page read gave only the TTL and email binding; acceptance flow,
  revocation, expiry behaviour and multi-organization users are unverified.
- Whether any vendor accepts an invitation purely by matching the email at
  passwordless sign-in with no token or link parameter: unverified; none of the
  fetched pages describes it, and the vendor flows read do rely on a link or
  code (WorkOS) or an account-level verified-email match (GitHub).
- Whether a newer magic link invalidates the previous one, and what should
  happen when an older or used link is clicked: unverified. The OWASP Forgot
  Password extract did not cover either.
- Lazy versus scheduled expiry: unanswered.
- Landing-tenant choice when several Tenants activate at once: unanswered.
- A "declined/rejected" status in any vendor: unverified.
- Whether Admin-side responses should hide that an email already exists as a
  User: unanswered.
- Pessimistic locking / isolation-level guidance for concurrent accepts: not
  fetched.
- Unicode and provider-specific email normalization: unverified.
- Repo inconsistencies (noted, not changed): `CONTEXT.md` (Pending Membership:
  "no token and no expiry") and ADR-0008 (columns without `status`; "deleted on
  that email's first sign-in"; "no TTL by design") no longer match the design
  under evaluation (status column, keep-as-`accepted`, 7-day expiry).
