import "server-only";

import { cookies } from "next/headers";
import { notFound, redirect } from "next/navigation";
import { cache } from "react";

import { getSessionIdentity } from "@/lib/session_identity";

/**
 * Server-only gate for everything under `/w/{slug}`: forwards the request's
 * cookie into GET /me (coding-standards §4.2) and returns the Tenant and
 * Profile the shell and its pages render. Wrapped in `cache` so the layout
 * and the page share one /me call per request.
 *
 * - Invalid/expired session -> sign-in.
 * - No Tenant Membership at all -> onboarding.
 * - A slug the caller isn't a member of -> 404, the same as one that doesn't
 *   exist, so a slug can't be probed.
 */
export const resolveWorkspace = cache(async (slug: string) => {
  const cookieHeader = (await cookies()).toString();
  const identity = await getSessionIdentity(cookieHeader);

  if (!identity) {
    redirect("/sign-in");
  }
  if (identity.memberships.length === 0) {
    redirect("/onboarding");
  }

  const membership = identity.memberships.find((m) => m.tenant_slug === slug);
  if (!membership) {
    notFound();
  }

  return {
    tenantId: membership.tenant_id,
    tenantName: membership.tenant_name,
    tenantSlug: membership.tenant_slug,
    role: membership.role,
    profile: identity.profile,
  };
});
