import { apiFetch } from "@/lib/api_client";

import { startedUploadSchema, type StartedUpload } from "../types";

/** POST /uploads/init: creates a pending Upload and returns the presigned
 * PUT. A 422 carries the reason the file was refused. */
export async function startUpload(
  tenantId: string,
  file: { name: string; size: number; type: string },
  sha256: string,
): Promise<StartedUpload> {
  const data = await apiFetch("/api/v1/uploads/init", {
    method: "POST",
    credentials: "include",
    headers: { "X-Tenant-ID": tenantId },
    body: {
      filename: file.name,
      size: file.size,
      content_type: file.type,
      sha256,
    },
  });
  return startedUploadSchema.parse(data);
}
