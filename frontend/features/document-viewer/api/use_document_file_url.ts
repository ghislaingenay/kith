"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchDocumentFileUrl } from "./fetch_document_file_url";

/** The Document's presigned link, fetched only while `enabled`. Never kept
 * in the cache: the link expires, so each opening asks for a fresh one. */
export function useDocumentFileUrl(
  tenantId: string,
  documentId: string,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["document-file-url", tenantId, documentId],
    queryFn: () => fetchDocumentFileUrl(tenantId, documentId),
    enabled,
    gcTime: 0,
    staleTime: 0,
  });
}
