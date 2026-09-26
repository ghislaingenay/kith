"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";

import type { LibraryDocument, LibrarySummary } from "../types";
import { fetchDocuments, fetchDocumentsSummary } from "./fetch_library";

const POLL_MS = 5000;
const IN_PROGRESS_STATUSES = ["uploaded", "processing"];

/** Prefix of both library queries, so an accepted upload can refresh them. */
export const libraryQueryKey = (tenantId: string) =>
  ["documents", tenantId] as const;

/** The library's Documents and banner counts. Ingestion runs in the
 * background, so both are refetched every few seconds while either one still
 * shows work in progress, and left alone once both agree everything has
 * settled. Each polls on the other's say-so too, so a row never stays stuck
 * on "Processing" after the banner has gone. */
export function useLibrary(tenantId: string) {
  const queryClient = useQueryClient();
  const summaryKey = [...libraryQueryKey(tenantId), "summary"];
  const listKey = [...libraryQueryKey(tenantId), "list"];

  // Read from the cache, not the hook results: react-query asks for the
  // interval while the queries are still being created.
  const pollWhileInProgress = () => {
    const summary = queryClient.getQueryData<LibrarySummary>(summaryKey);
    const documents = queryClient.getQueryData<LibraryDocument[]>(listKey);
    const inProgress =
      (summary?.in_progress ?? 0) > 0 ||
      (documents?.some((document) =>
        IN_PROGRESS_STATUSES.includes(document.ingestion_status),
      ) ??
        false);
    return inProgress ? POLL_MS : false;
  };

  const summary = useQuery({
    queryKey: summaryKey,
    queryFn: () => fetchDocumentsSummary(tenantId),
    refetchInterval: pollWhileInProgress,
  });
  const documents = useQuery({
    queryKey: listKey,
    queryFn: () => fetchDocuments(tenantId),
    refetchInterval: pollWhileInProgress,
  });
  return { summary, documents };
}
