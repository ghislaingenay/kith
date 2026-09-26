import { z } from "zod";

import { apiFetch } from "@/lib/api_client";

import {
  libraryDocumentSchema,
  librarySummarySchema,
  type LibraryDocument,
  type LibrarySummary,
} from "../types";

const getOptions = (tenantId: string) => ({
  credentials: "include" as const,
  headers: { "X-Tenant-ID": tenantId },
});

/** GET /documents: the Tenant's Documents, newest first. */
export async function fetchDocuments(
  tenantId: string,
): Promise<LibraryDocument[]> {
  const data = await apiFetch("/api/v1/documents", getOptions(tenantId));
  return z.array(libraryDocumentSchema).parse(data);
}

/** GET /documents/summary: how many Documents are in progress or failed. */
export async function fetchDocumentsSummary(
  tenantId: string,
): Promise<LibrarySummary> {
  const data = await apiFetch(
    "/api/v1/documents/summary",
    getOptions(tenantId),
  );
  return librarySummarySchema.parse(data);
}
