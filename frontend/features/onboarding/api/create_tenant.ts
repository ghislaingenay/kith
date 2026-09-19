import { apiFetch } from "@/lib/api_client";

import { createTenantResponseSchema, type CreateTenantResponse } from "../types";

/** POST /tenants: creates the Tenant and the caller's Owner
 * TenantMembership in one call. A 400 here means the caller already has an
 * active membership (TenantAlreadyExistsError) — surfaced via the backend's
 * own message rather than a bespoke error type, since there's nothing else
 * the form can do differently with it. */
export async function createTenant(name: string): Promise<CreateTenantResponse> {
  const data = await apiFetch("/tenants", {
    method: "POST",
    credentials: "include",
    body: { name },
  });
  return createTenantResponseSchema.parse(data);
}
