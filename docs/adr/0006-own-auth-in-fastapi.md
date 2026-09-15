---
status: accepted
date: 2026-09-14
supersedes: ADR-0003
---

# FastAPI owns authentication: Google OAuth via authlib, magic links, Redis sessions

FastAPI implements sign-in itself. Google OAuth uses `authlib` (state, PKCE and ID-token verification handled by the library). Magic links are single-use tokens, stored hashed in Redis with a 15-minute TTL and sent through the `Mailer`. A session is an opaque random id (32 bytes) carried in an httpOnly, Secure, SameSite=Lax cookie set on the parent domain so both the `app.` and `api.` hosts see it. Redis stores only the SHA-256 of that id, keyed `session:{hash}`, with a 30-day sliding TTL; the raw id exists only in the browser's cookie. Sessions are rotated on login. Next.js is a client: its middleware checks for the cookie and calls `GET /me`; it holds no identity state and no database connection. Users, Profiles and OAuth account links live only in the project's Postgres.

Why: the constraint is one identity store in the project's own Postgres, the backend already owns the domain, and the browser already talks to FastAPI directly. Any Node-side auth library (next-auth, Better Auth) would exist only to hand identity across a boundary this architecture does not otherwise have, at the cost of an adapter or a second ORM plus a token-minting route (see ADR-0003). External identity providers were rejected: hosted ones add per-user pricing and lock-in for 50 people who sign in with Google, and self-hosted ones (Keycloak, Ory) are heavier than the application.

## Consequences

- The project owns the security of two flows. The known sharp edges and their mitigations: OAuth state and PKCE (library), magic-link replay (hashed, deleted on use, rate limited per email), session fixation (rotate on login), CSRF on state-changing requests (SameSite cookie plus an Origin check on the API), enumeration via magic-link requests (same response whether or not the email exists).
- Adding another provider (GitHub, Microsoft) is a second `authlib` client and a row in the OAuth accounts table, not a plugin.
- Revoking a session or a membership is a Redis delete; it takes effect on the next request.
- Because Redis holds hashes, a leaked Redis dump or backup cannot be replayed as live cookies. The cost is one SHA-256 per request, and that a session cannot be enumerated back to its cookie value (there is no "copy this session" support path, which is intended).
- Next.js Server Components and Route Handlers that call the API must forward the incoming request's cookie header themselves (server-side `fetch` has no cookie jar), and only FastAPI ever sets or clears the cookie. A `Set-Cookie` on a response to a server-side fetch is dropped, so the sliding expiry is refreshed on browser-direct requests only.
- `POST /auth/sync` and the bearer-token route from ADR-0003 do not exist. The API surface gains `GET /auth/google`, `GET /auth/google/callback`, `POST /auth/magic-link`, `GET /auth/magic-link/verify`, `POST /auth/logout`.
- Because the API and the app must share a parent domain for the cookie, local development runs both behind Caddy on one hostname (or uses a `localhost` cookie with the same ports), not on bare `localhost:3000` and `localhost:8000`.
