"use client";

import { useLibrary } from "../api/use_library";
import type { LibraryDocument, LibrarySummary } from "../types";
import {
  capitalize,
  formatDate,
  formatFileSize,
} from "../utils/format_library";

/** The Uploads Library: what the Tenant holds and how far each Document has
 * got through Ingestion. */
export function UploadsLibrary({ tenantId }: { readonly tenantId: string }) {
  const { summary, documents } = useLibrary(tenantId);

  return (
    <section className="w-full max-w-4xl" aria-label="Uploaded documents">
      {summary.data && <ProcessingBanner summary={summary.data} />}
      {documents.isPending && (
        <p className="text-sm text-muted-foreground">Loading documents…</p>
      )}
      {documents.isError && (
        <p role="alert" className="text-sm text-destructive">
          {documents.error.message}
        </p>
      )}
      {documents.data &&
        (documents.data.length === 0 ? (
          <EmptyState />
        ) : (
          <DocumentsTable documents={documents.data} />
        ))}
    </section>
  );
}

function ProcessingBanner({ summary }: { readonly summary: LibrarySummary }) {
  const { in_progress, failed } = summary;
  if (in_progress === 0 && failed === 0) return null;

  return (
    <p
      role="status"
      className="mb-4 rounded-lg border bg-muted px-4 py-3 text-sm"
    >
      {in_progress > 0 &&
        `${countFiles(in_progress)} ${in_progress === 1 ? "is" : "are"} still processing. Answers may be incomplete for the newest ones. `}
      {failed > 0 && `${countFiles(failed)} failed to process.`}
    </p>
  );
}

function EmptyState() {
  return (
    <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      <p className="font-medium text-foreground">No documents yet</p>
      <p>Uploaded PDFs will appear here.</p>
    </div>
  );
}

function DocumentsTable({
  documents,
}: {
  readonly documents: readonly LibraryDocument[];
}) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-left text-sm">
        <thead className="border-b text-muted-foreground">
          <tr>
            {COLUMNS.map((column) => (
              <th key={column} scope="col" className="px-4 py-2 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {documents.map((document) => (
            <DocumentRow key={document.id} document={document} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentRow({ document }: { readonly document: LibraryDocument }) {
  const { ingestion_stage, pages_extracted, page_count } = document;

  return (
    <tr>
      <td className="max-w-64 truncate px-4 py-3">{document.name}</td>
      <td className="whitespace-nowrap px-4 py-3">
        {formatFileSize(document.size_bytes)}
      </td>
      <td className="px-4 py-3">{document.uploader}</td>
      <td className="whitespace-nowrap px-4 py-3">
        {formatDate(document.created_at)}
      </td>
      <td className="px-4 py-3">
        <span className="font-medium">
          {capitalize(document.ingestion_status)}
        </span>
        {ingestion_stage && (
          <span className="block text-xs text-muted-foreground">
            {capitalize(ingestion_stage)}
          </span>
        )}
        {pages_extracted !== null && (
          <span className="block text-xs text-muted-foreground">
            {pages_extracted} of {page_count} pages
          </span>
        )}
      </td>
    </tr>
  );
}

function countFiles(count: number): string {
  return `${count} ${count === 1 ? "file" : "files"}`;
}

const COLUMNS = ["Name", "Size", "Uploaded By", "Date", "Status"];
