const KB = 1024;
const MB = KB * 1024;

/** "512 B", "2.0 KB", "1.5 MB": the sizes an upload (max 20 MB) can have. */
export function formatFileSize(bytes: number): string {
  if (bytes < KB) return `${bytes} B`;
  if (bytes < MB) return `${(bytes / KB).toFixed(1)} KB`;
  return `${(bytes / MB).toFixed(1)} MB`;
}

/** "Sep 1, 2026", in the viewer's time zone. */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/** "processing" -> "Processing". */
export function capitalize(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}
