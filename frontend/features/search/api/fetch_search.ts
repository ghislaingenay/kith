import { apiFetch } from "@/lib/api_client";

import { searchResponseSchema, type SearchResponse } from "../types";

/** POST /search: up to 20 ranked passages of the Tenant's Documents. */
export async function fetchSearch(
  tenantId: string,
  query: string,
): Promise<SearchResponse> {
  const data = await apiFetch("/api/v1/search", {
    method: "POST",
    credentials: "include",
    headers: { "X-Tenant-ID": tenantId },
    body: { query },
  });
  return searchResponseSchema.parse(data);
}
