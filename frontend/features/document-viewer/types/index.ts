import { z } from "zod";

/** A short-lived presigned link to a Document's PDF
 * (GET /documents/{id}/file-url). */
export const documentFileUrlSchema = z.object({
  url: z.string().url(),
  expires_in: z.number(),
});

export type DocumentFileUrl = Readonly<z.infer<typeof documentFileUrlSchema>>;
