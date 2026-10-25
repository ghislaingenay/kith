import { useState } from "react";

import { DocumentViewerDialog } from "@/features/document-viewer";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api_client";

import type { SearchResponse, SearchResult } from "../types";
import { documentsLabel } from "../utils/documents_label";
import { parseHighlight } from "../utils/parse_highlights";

/** The Search's states: loading, error, no match, or the ranked passages. */
export function SearchResults({
  tenantId,
  query,
  documentCount,
  isPending,
  error,
  data,
  onRetry,
}: {
  readonly tenantId: string;
  readonly query: string;
  readonly documentCount: number | undefined;
  readonly isPending: boolean;
  readonly error: Error | null;
  readonly data: SearchResponse | undefined;
  readonly onRetry: () => void;
}) {
  // Local state, so closing the viewer leaves the URL and results untouched.
  const [opened, setOpened] = useState<SearchResult | null>(null);

  if (isPending) return <SearchingLine documentCount={documentCount} />;
  if (error) return <SearchFailure error={error} onRetry={onRetry} />;
  if (!data) return null;
  return (
    <div className="space-y-3">
      {data.degraded && (
        <p role="status" className="text-xs text-muted-foreground">
          Showing keyword matches only
        </p>
      )}
      {data.results.length === 0 ? (
        <p className="py-8 text-sm text-muted-foreground">No passages match “{query}”.</p>
      ) : (
        <ol aria-label="Search results" className="-mx-3 space-y-1">
          {data.results.map((result) => (
            <li key={result.chunk_id}>
              <button
                type="button"
                aria-label={`Open ${result.document_name} at page ${result.page_number}`}
                onClick={() => setOpened(result)}
                className="group w-full cursor-pointer rounded-md px-3 py-3 text-left hover:bg-muted/50 focus-visible:bg-muted/50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-ring"
              >
                <ResultRow result={result} />
              </button>
            </li>
          ))}
        </ol>
      )}
      {opened && (
        <DocumentViewerDialog
          tenantId={tenantId}
          documentId={opened.document_id}
          documentName={opened.document_name}
          initialPage={opened.page_number}
          open
          onOpenChange={(open) => {
            if (!open) setOpened(null);
          }}
        />
      )}
    </div>
  );
}

function ResultRow({ result }: { readonly result: SearchResult }) {
  return (
    <>
      <p className="text-base font-medium text-primary">
        <span className="underline-offset-4 group-hover:underline">{result.document_name}</span>
        <span className="ml-2 font-mono text-xs font-normal text-muted-foreground">
          Page {result.page_number}
        </span>
      </p>
      <p className="mt-1 font-serif text-[0.95rem] leading-relaxed text-foreground/80">
        {result.highlights.length > 0 ? (
          result.highlights.map((fragment, index) => (
            <span key={index} className="mr-1">
              {parseHighlight(fragment).map((segment, i) =>
                segment.marked ? (
                  <mark key={i} className="rounded-sm bg-highlight text-highlight-foreground">
                    {segment.text}
                  </mark>
                ) : (
                  segment.text
                ),
              )}
            </span>
          ))
        ) : (
          <span className="line-clamp-3 whitespace-pre-line">{result.text}</span>
        )}
      </p>
    </>
  );
}

function SearchingLine({ documentCount }: { readonly documentCount: number | undefined }) {
  return (
    <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
      Searching {documentCount === undefined ? "documents" : documentsLabel(documentCount)}…
    </p>
  );
}

function SearchFailure({
  error,
  onRetry,
}: {
  readonly error: Error;
  readonly onRetry: () => void;
}) {
  const status = error instanceof ApiError ? error.status : null;
  if (status === 429) {
    return (
      <p role="alert" className="text-sm text-destructive">
        You are searching too fast. Wait a moment and try again.
      </p>
    );
  }
  return (
    <div role="alert" className="flex items-center gap-3 text-sm text-destructive">
      <p>
        {status === 503
          ? "Search is unavailable right now."
          : "Search failed. Please try again."}
      </p>
      <Button type="button" variant="outline" size="sm" onClick={onRetry}>
        Retry
      </Button>
    </div>
  );
}
