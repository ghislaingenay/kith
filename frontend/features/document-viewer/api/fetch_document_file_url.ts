import { apiFetch } from "@/lib/api_client";

import { documentFileUrlSchema, type DocumentFileUrl } from "../types";

/** GET /documents/{id}/file-url: where the browser may read the Document's
 * PDF from, for a few minutes. */
export async function fetchDocumentFileUrl(
  tenantId: string,
  documentId: string,
): Promise<DocumentFileUrl> {
  const data = await apiFetch(`/api/v1/documents/${documentId}/file-url`, {
    credentials: "include",
    headers: { "X-Tenant-ID": tenantId },
  });
  return documentFileUrlSchema.parse(data);
}
