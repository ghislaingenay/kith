export const MAX_PDF_BYTES = 20 * 1024 * 1024;
export const PDF_CONTENT_TYPE = "application/pdf";

/** Mirrors the API's *default* start-of-upload rules (`backend/app/documents/service.py`) so an obviously bad
 * file is refused before any bytes move. Returns the message to show, or null
 * when the file is fine. */
export function validatePdfFile(file: File): string | null {
  if (file.type !== PDF_CONTENT_TYPE) {
    return "Only PDF files can be uploaded.";
  }
  if (file.size > MAX_PDF_BYTES) {
    return `File must be ${MAX_PDF_BYTES / (1024 * 1024)} MB or smaller.`;
  }
  return null;
}
