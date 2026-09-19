import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getSessionIdentity, workspacePath } from "@/lib/session_identity";

import { suggestWorkspaceName } from "../utils/suggest_workspace_name";

/**
 * Server-only gate for the onboarding route: forwards the incoming
 * request's cookie header into GET /me (coding-standards §4.2 — server
 * fetches have no cookie jar of their own) and decides whether this visitor
 * should actually see the form.
 *
 * `middleware.ts` already guarantees a session cookie is present for this
 * route; this additionally validates it and applies onboarding-specific
 * business rules that don't belong in the centralized gate:
 *
 * - Invalid/expired session -> bounce to sign-in.
 * - Already has a Tenant Membership -> nothing to onboard, send them to
 *   their workspace instead (also avoids a guaranteed
 *   TenantAlreadyExistsError on submit).
 * - Otherwise -> a suggested workspace name derived from their email.
 */
export async function resolveOnboardingAccess(): Promise<{
  suggestedWorkspaceName: string;
}> {
  const cookieHeader = (await cookies()).toString();
  const identity = await getSessionIdentity(cookieHeader);

  if (!identity) {
    redirect("/sign-in");
  }
  if (identity.memberships.length > 0) {
    redirect(workspacePath(identity.memberships[0].tenant_slug));
  }

  return { suggestedWorkspaceName: suggestWorkspaceName(identity.user.email) };
}
