/** "1 document" / "3 documents", for the count hint and the loading line. */
export function documentsLabel(count: number): string {
  return `${count} ${count === 1 ? "document" : "documents"}`;
}
