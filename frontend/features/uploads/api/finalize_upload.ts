import { apiFetch } from "@/lib/api_client";

import { documentSchema, type UploadedDocument } from "../types";

/** POST /uploads/{id}/finalize: the API validates the stored file and turns
 * it into a Document. Safe to call again for the same Upload. */
export async function finalizeUpload(
  tenantId: string,
  uploadId: string,
): Promise<UploadedDocument> {
  const data = await apiFetch(`/api/v1/uploads/${uploadId}/finalize`, {
    method: "POST",
    credentials: "include",
    headers: { "X-Tenant-ID": tenantId },
  });
  return documentSchema.parse(data);
}
