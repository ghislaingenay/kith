import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api_client";

import type { SearchResponse, SearchResult } from "../types";
import { parseHighlight } from "../utils/parse_highlights";

/** The Search's states: loading, error, no match, or the ranked passages. */
export function SearchResults({
  query,
  isPending,
  error,
  data,
  onRetry,
}: {
  readonly query: string;
  readonly isPending: boolean;
  readonly error: Error | null;
  readonly data: SearchResponse | undefined;
  readonly onRetry: () => void;
}) {
  if (isPending) return <LoadingRows />;
  if (error) return <SearchFailure error={error} onRetry={onRetry} />;
  if (!data) return null;
  if (data.results.length === 0) {
    return (
      <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        No passages match “{query}”.
      </p>
    );
  }
  return (
    <ol aria-label="Search results" className="divide-y rounded-lg border">
      {data.results.map((result) => (
        <li key={result.chunk_id} className="px-4 py-3">
          <ResultRow result={result} />
        </li>
      ))}
    </ol>
  );
}

function ResultRow({ result }: { readonly result: SearchResult }) {
  return (
    <>
      <p className="text-sm font-medium">
        {result.document_name}
        <span className="ml-2 font-normal text-muted-foreground">
          Page {result.page_number}
        </span>
      </p>
      <p className="mt-1 text-sm text-muted-foreground">
        {result.highlights.length > 0 ? (
          result.highlights.map((fragment, index) => (
            <span key={index} className="mr-1">
              {parseHighlight(fragment).map((segment, i) =>
                segment.marked ? (
                  <mark key={i} className="rounded bg-yellow-200 text-foreground dark:bg-yellow-500/40">
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

function LoadingRows() {
  return (
    <div role="status" aria-label="Searching" className="space-y-3">
      {[0, 1, 2].map((row) => (
        <Skeleton key={row} className="h-16 w-full" />
      ))}
    </div>
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
