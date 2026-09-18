import { z } from "zod";

import { ApiError, apiFetch } from "./api_client";

/** Must match the backend's `SESSION_COOKIE_NAME` (`auth/config.py`) —
 * there is no shared package between the two, so this is the frontend's
 * single point of truth for the cookie's name. */
export const SESSION_COOKIE_NAME = "kith_session";

export const sessionIdentitySchema = z.object({
  user: z.object({ email: z.string().email() }),
  memberships: z.array(z.object({ tenant_slug: z.string() })),
});

export type SessionIdentity = Readonly<z.infer<typeof sessionIdentitySchema>>;

/**
 * Forwards a cookie header into GET /me and returns the caller's identity
 * plus active Tenant Memberships. Shared by every Server Component/Route
 * Handler that needs to decide where a visitor lands (coding-standards
 * §4.2 — centralize this instead of a per-route fetch+schema copy).
 *
 * Returns `null` only when the session itself is invalid (a 401) — a
 * backend outage or network failure is rethrown rather than silently
 * treated as "not signed in", since those aren't the same situation for a
 * caller deciding whether to bounce someone to /sign-in.
 */
export async function getSessionIdentity(
  cookieHeader: string,
): Promise<SessionIdentity | null> {
  let data: unknown;
  try {
    data = await apiFetch("/me", {
      headers: { cookie: cookieHeader },
      cache: "no-store",
    });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      return null;
    }
    throw err;
  }

  const parsed = sessionIdentitySchema.safeParse(data);
  return parsed.success ? parsed.data : null;
}

export function workspacePath(tenantSlug: string): string {
  return `/w/${tenantSlug}`;
}
