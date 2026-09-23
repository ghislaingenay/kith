import { apiFetch } from "@/lib/api_client";

/** POST /auth/logout: the API clears the session cookie and deletes the
 * session. Idempotent, so it succeeds even for an already-expired session. */
export async function signOut(): Promise<void> {
  await apiFetch("/api/v1/auth/logout", {
    method: "POST",
    credentials: "include",
  });
}
