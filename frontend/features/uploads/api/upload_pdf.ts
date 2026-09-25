import type { UploadedDocument } from "../types";
import { sha256Hex } from "../utils/sha256_hex";
import { finalizeUpload } from "./finalize_upload";
import { sendToStorage } from "./send_to_storage";
import { startUpload } from "./start_upload";

/** Init, direct PUT to storage, finalize. The file is read once so the bytes
 * that are hashed are the bytes that are sent. */
export async function uploadPdf(
  tenantId: string,
  file: File,
): Promise<UploadedDocument> {
  const bytes = await file.arrayBuffer();
  const started = await startUpload(tenantId, file, await sha256Hex(bytes));
  await sendToStorage(started.url, started.headers, bytes);
  return finalizeUpload(tenantId, started.upload_id);
}
