import { apiFetch } from "@/lib/api_client";

/** DELETE /documents/{id}: soft-deletes one Document. */
export async function deleteDocument(
  tenantId: string,
  documentId: string,
): Promise<void> {
  await apiFetch(`/api/v1/documents/${documentId}`, {
    method: "DELETE",
    credentials: "include",
    headers: { "X-Tenant-ID": tenantId },
  });
}
