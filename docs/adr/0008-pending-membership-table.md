---
status: accepted
date: 2026-09-17
---

# Pending Membership is its own Postgres table, not Redis or a new datastore

`tenant_memberships.user_id` is `NOT NULL`, so an email invited before it has signed in has nowhere to live in that table. We add a dedicated `pending_memberships` table (tenant_id, email, role, invited_by, created_at) in the existing Postgres, converted into a real `TenantMembership` row and deleted on that email's first sign-in.

Why: Redis (already used for sessions and magic links) would lose a Pending Membership on eviction or a restart, and a Pending Membership has no TTL by design (`CONTEXT.md`: "no token and no expiry") so it can't lean on Redis's expiry model to paper over that. MongoDB's TTL indexes would solve the durability problem but introduce a second database for one small table. Postgres is already the system of record for Users and Tenants, needs no new infrastructure, and gives the row the same durability guarantees as everything else membership-related.
