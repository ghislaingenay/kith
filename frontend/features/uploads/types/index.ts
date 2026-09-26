import { z } from "zod";

/** Where and how to send the file: PUT the bytes to `url` with exactly
 * these `headers`, then finalize (POST /uploads/init). */
export const startedUploadSchema = z.object({
  upload_id: z.string(),
  url: z.string().url(),
  headers: z.record(z.string(), z.string()),
});

export type StartedUpload = Readonly<z.infer<typeof startedUploadSchema>>;

/** The Document a finalized Upload produced (POST /uploads/{id}/finalize). */
export const documentSchema = z.object({
  id: z.string(),
  name: z.string(),
  size_bytes: z.number(),
  page_count: z.number(),
  content_hash: z.string(),
  ingestion_status: z.string(),
});

export type UploadedDocument = Readonly<z.infer<typeof documentSchema>>;

/** One row of the Uploads Library (GET /documents). The Stage and page
 * progress stay null until the ingestion worker writes them. */
export const libraryDocumentSchema = z.object({
  id: z.string(),
  name: z.string(),
  size_bytes: z.number(),
  uploader: z.string(),
  created_at: z.string(),
  ingestion_status: z.string(),
  ingestion_stage: z.string().nullable(),
  pages_extracted: z.number().nullable(),
  page_count: z.number(),
});

export type LibraryDocument = Readonly<z.infer<typeof libraryDocumentSchema>>;

/** Counts behind the library banner (GET /documents/summary). */
export const librarySummarySchema = z.object({
  in_progress: z.number(),
  failed: z.number(),
});

export type LibrarySummary = Readonly<z.infer<typeof librarySummarySchema>>;
