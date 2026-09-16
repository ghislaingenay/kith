---
status: accepted
date: 2026-09-16
---

# Four fixed Roles as a column and a pure function, not permission tables

A Tenant Membership carries its Role as a string column constrained to `owner`, `admin`, `member`, `viewer`. The permission matrix (which Role may do which action) is a pure function in the tenancy domain, tested in isolation. The generic `roles`, `permissions` and `role_permissions` tables inherited from business-os, their seed script and the Redis role cache refreshed at startup are removed.

Why: the MVP has eight actions and four Roles that no user can edit. Tables, a seed and a cache for that are overhead on every request and a second source of truth that can drift from the product's permission table in `docs/design/mvp-design.md`.

## Considered options

- Keep the tables and reseed them with the four Roles. Rejected: nothing reads them that a function cannot answer, and a per-Tenant seed step would be needed the day roles become Tenant-scoped anyway.
- Create a Tenant-scoped `roles` table now with four system rows per Tenant, referenced by foreign key. Rejected: it buys nothing today and adds a seed step to Tenant creation and a join to every permission check.

## Consequences

- Tenant-defined Roles remain possible. The named path is expand-contract: add a Tenant-scoped roles table, widen the membership column to hold either a built-in name or a custom role id, and give the permission function a branch that reads the custom definition. Nothing in the MVP should assume the column can only ever hold the four names.
- Pending Memberships store the same Role string, so the constraint lives in both tables.
