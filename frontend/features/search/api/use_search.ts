"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchSearch } from "./fetch_search";

const STALE_MS = 5 * 60 * 1000;

/** Prefix of every Search query of a Tenant, so an upload or delete can
 * invalidate them all. */
export const searchQueryKey = (tenantId: string) =>
  ["search", tenantId] as const;

/** Runs the Search for a Query; a blank Query does nothing. Failures are not
 * retried automatically: a 429 or 503 should wait for the Member's Retry. */
export function useSearch(tenantId: string, query: string) {
  return useQuery({
    queryKey: [...searchQueryKey(tenantId), query],
    queryFn: () => fetchSearch(tenantId, query),
    enabled: query !== "",
    staleTime: STALE_MS,
    retry: false,
  });
}
