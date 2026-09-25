/** PUTs the file's bytes to the presigned URL. Plain `fetch`: this goes to
 * the storage host, not the API, so there is no API base URL or session
 * cookie to add. */
export async function sendToStorage(
  url: string,
  headers: Readonly<Record<string, string>>,
  bytes: ArrayBuffer,
): Promise<void> {
  const response = await fetch(url, { method: "PUT", headers, body: bytes });
  if (!response.ok) {
    throw new Error("The file could not be sent. Please try again.");
  }
}
