"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchDocuments } from "./fetch_library";
import { libraryQueryKey } from "./use_library";

/** Whether the Tenant has any Document yet, and how many; `undefined` until
 * known. Shares the Uploads Library's list cache, so an accepted upload
 * updates it. */
export function useHasDocuments(tenantId: string) {
  const documents = useQuery({
    queryKey: [...libraryQueryKey(tenantId), "list"],
    queryFn: () => fetchDocuments(tenantId),
  });
  return {
    hasDocuments: documents.data ? documents.data.length > 0 : undefined,
    documentCount: documents.data?.length,
    isError: documents.isError,
  };
}
