import type { HttpHandler } from "msw";

/** Default MSW handlers, shared across every unit test. Empty on purpose —
 * feature tests add the endpoints they exercise via `server.use()`, keeping
 * the mocked request/response shapes next to the test that relies on them
 * (coding-standards §7: feature `api/` modules are the only thing that
 * should need mocking). */
export const handlers: HttpHandler[] = [];
