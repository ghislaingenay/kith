---
status: superseded by ADR-0006
date: 2026-09-14
---

# Identity is owned by next-auth; FastAPI trusts a short-lived shared-secret JWT

Superseded the same day by ADR-0006 before any code was written. Kept because the reasoning still explains why a Node-side auth library was rejected.

The proposal was: next-auth in Next.js owns sign-in (Google OAuth and magic links), calls FastAPI `POST /auth/sync` on sign-in, and the browser carries a 15-minute HS256 JWT minted by a Next.js route handler, verified by FastAPI with a shared secret. Magic-link tokens in Redis via a custom adapter.

Why it was dropped: the constraint that Users live only in the project's Postgres, with FastAPI as the domain owner and the browser already calling FastAPI directly, made next-auth a middleman. Every variant (custom adapter forwarding to FastAPI, Prisma mapped onto FastAPI's tables with a drift check, or duplicate user tables with a sync) added either bespoke code on the login path or a second ORM on one schema, plus a token-minting route to get around next-auth's encrypted session cookie.
