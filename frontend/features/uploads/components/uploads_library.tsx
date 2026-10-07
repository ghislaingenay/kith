"use client";

import { useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DocumentViewerDialog } from "@/features/document-viewer";

import {
  useDeleteDocuments,
  type RefusedDeletion,
} from "../api/use_delete_documents";
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
  const deletion = useDeleteDocuments(tenantId);
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(new Set());
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [nameFilter, setNameFilter] = useState("");
  const [previewed, setPreviewed] = useState<LibraryDocument | null>(null);

  // The library is unpaginated and capped, so the browser filters what it
  // already holds; this moves to the server once that Limit is lifted.
  const shown = (documents.data ?? []).filter((document) =>
    document.name.toLowerCase().includes(nameFilter.toLowerCase()),
  );
  // Only what is shown can be deleted, so a hidden row is never lost by surprise.
  const selected = shown.filter((document) => selectedIds.has(document.id));

  const toggle = (id: string) =>
    setSelectedIds((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });

  const deleteSelected = () => {
    const count = selected.length;
    deletion.reset();
    deletion.mutate(selected, {
      onSuccess: (refused) => {
        if (refused.length === 0) {
          toast.success(count === 1 ? "Document deleted" : `${count} documents deleted`);
        } else if (refused.length === count) {
          toast.error(count === 1 ? "Could not delete document" : "Could not delete documents");
        } else {
          toast.warning(`Deleted ${count - refused.length} of ${count} documents`);
        }
      },
      onError: () => {
        toast.error(count === 1 ? "Could not delete document" : "Could not delete documents");
      },
    });
    setSelectedIds((current) => {
      const next = new Set(current);
      for (const { id } of selected) next.delete(id);
      return next;
    });
    setConfirmingDelete(false);
  };

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
          <>
            <div className="mb-2 flex items-center justify-between gap-2">
              <Input
                aria-label="Filter by name"
                placeholder="Filter by name…"
                className="max-w-64"
                value={nameFilter}
                onChange={(event) => setNameFilter(event.target.value)}
              />
              <AlertDialog open={confirmingDelete} onOpenChange={setConfirmingDelete}>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={selected.length === 0 || deletion.isPending}
                  onClick={() => setConfirmingDelete(true)}
                >
                  {`Delete selected (${selected.length})`}
                </Button>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>
                      {selected.length === 1
                        ? "Delete this document?"
                        : `Delete ${selected.length} documents?`}
                    </AlertDialogTitle>
                    <AlertDialogDescription>
                      This can&apos;t be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction variant="destructive" onClick={deleteSelected}>
                      Delete
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
            {deletion.data && deletion.data.length > 0 && (
              <RefusedDeletions refused={deletion.data} />
            )}
            {shown.length === 0 ? (
              <NoNameMatch filter={nameFilter} />
            ) : (
              <DocumentsTable
                documents={shown}
                selectedIds={selectedIds}
                onToggle={toggle}
                onPreview={setPreviewed}
              />
            )}
          </>
        ))}
      {previewed && (
        <DocumentViewerDialog
          tenantId={tenantId}
          documentId={previewed.id}
          documentName={previewed.name}
          open
          onOpenChange={(open) => {
            if (!open) setPreviewed(null);
          }}
        />
      )}
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

function NoNameMatch({ filter }: { readonly filter: string }) {
  return (
    <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
      No document matches “{filter}”.
    </p>
  );
}

function RefusedDeletions({
  refused,
}: {
  readonly refused: readonly RefusedDeletion[];
}) {
  return (
    <div role="alert" className="mb-4 text-sm text-destructive">
      <p>Could not delete:</p>
      <ul className="list-disc pl-5">
        {refused.map(({ id, name, reason }) => (
          <li key={id}>
            {name}: {reason}
          </li>
        ))}
      </ul>
    </div>
  );
}

function DocumentsTable({
  documents,
  selectedIds,
  onToggle,
  onPreview,
}: {
  readonly documents: readonly LibraryDocument[];
  readonly selectedIds: ReadonlySet<string>;
  readonly onToggle: (id: string) => void;
  readonly onPreview: (document: LibraryDocument) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-left text-sm">
        <thead className="border-b text-muted-foreground">
          <tr>
            <th scope="col" className="w-10 px-4 py-2">
              <span className="sr-only">Select</span>
            </th>
            {COLUMNS.map((column) => (
              <th key={column} scope="col" className="px-4 py-2 font-medium">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y">
          {documents.map((document) => (
            <DocumentRow
              key={document.id}
              document={document}
              isSelected={selectedIds.has(document.id)}
              onToggle={() => onToggle(document.id)}
              onPreview={() => onPreview(document)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DocumentRow({
  document,
  isSelected,
  onToggle,
  onPreview,
}: {
  readonly document: LibraryDocument;
  readonly isSelected: boolean;
  readonly onToggle: () => void;
  readonly onPreview: () => void;
}) {
  const { ingestion_stage, pages_extracted, page_count } = document;

  return (
    <tr>
      <td className="px-4 py-3">
        <input
          type="checkbox"
          aria-label={`Select ${document.name}`}
          checked={isSelected}
          onChange={onToggle}
        />
      </td>
      <td className="max-w-64 truncate px-4 py-3">
        <button
          type="button"
          className="max-w-full truncate text-left underline-offset-4 hover:underline"
          onClick={onPreview}
        >
          {document.name}
        </button>
      </td>
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
