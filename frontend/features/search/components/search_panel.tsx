"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { AskView, useAsk } from "@/features/ask";
import { useCreditBalance } from "@/features/credits";
import { useHasDocuments } from "@/features/uploads";

import { useSearch } from "../api/use_search";
import { documentsLabel } from "../utils/documents_label";
import { SearchResults } from "./search_results";

/** The dashboard's Search box and results. The URL (`?q=…&type=search`) holds
 * the Query, so refresh, Back and shared links all rerun the same Search. An
 * Ask is never in the URL, so a reload never charges again. With the Credit
 * Balance used up, Ask AI is disabled and Search still works (ADR-0017).
 *
 * Laid out like a search engine: before a Query, a large centred box under
 * the workspace name; once a Search or an Ask is shown, a slim top bar with
 * the results in a left-aligned reading column below. */
export function SearchPanel({
  tenantId,
  tenantName,
  canAsk,
}: {
  readonly tenantId: string;
  readonly tenantName: string;
  readonly canAsk: boolean;
}) {
  const params = useSearchParams();
  const pathname = usePathname();
  const { hasDocuments, documentCount, isError } = useHasDocuments(tenantId);
  const { state: askState, ask, reset: resetAsk } = useAsk(tenantId);
  // Until the balance is known, Ask AI stays enabled: the API refuses an Ask
  // with no Credits left anyway.
  const { data: balance } = useCreditBalance(tenantId, { enabled: canAsk });
  const noCreditsMessage = balance?.is_exhausted
    ? `${tenantName} has no credits left. Ask an Admin to request more. Search still works.`
    : null;

  // If the library check itself fails, show the box anyway and let the Search
  // report its own errors.
  if (hasDocuments === undefined && !isError) return null;
  if (hasDocuments === false) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-8 px-4 pb-[20vh] pt-16">
        <Wordmark tenantName={tenantName} />
        <Alert className="w-full max-w-2xl">
          <AlertTitle>No documents available</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>Upload a document to start searching.</p>
            <Button asChild>
              <Link href={`${pathname}/uploads`}>Go to uploads</Link>
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const activeQuery =
    params.get("type") === "search" ? (params.get("q") ?? "").trim() : "";

  const showsResult = activeQuery !== "" || askState.phase !== "idle";
  const searchBox = (
    // Keyed so Back or a shared link re-fills the box.
    <SearchBox
      key={activeQuery}
      size={showsResult ? "bar" : "hero"}
      initialQuery={activeQuery}
      canAsk={canAsk}
      isAsking={askState.phase === "streaming"}
      noCreditsMessage={noCreditsMessage}
      onSearch={resetAsk}
      onAsk={(query) => void ask(query)}
    />
  );

  // One tree for both layouts, so the box keeps its text and focus when a
  // Search or an Ask moves it from the centre to the top bar.
  return (
    <div
      className={cn(
        "flex flex-1 flex-col",
        !showsResult && "items-center justify-center px-4 pb-[20vh] pt-16",
      )}
    >
      <div
        className={cn(
          showsResult
            ? "border-b px-4 py-3 md:px-8"
            : "flex w-full max-w-2xl flex-col items-center gap-8",
        )}
      >
        <div
          className={cn(
            showsResult
              ? "flex max-w-[650px] flex-col gap-3 sm:flex-row sm:items-start"
              : "contents",
          )}
        >
          <Wordmark tenantName={tenantName} size={showsResult ? "bar" : "hero"} />
          <div className={showsResult ? "min-w-0 flex-1" : "w-full space-y-3"}>
            {searchBox}
            {!showsResult && documentCount !== undefined && (
              <p className="text-center text-sm text-muted-foreground">
                Search {documentsLabel(documentCount)}
              </p>
            )}
          </div>
        </div>
      </div>
      {showsResult && (
        <div className="w-full max-w-[650px] px-4 py-6 md:px-8">
          {askState.phase !== "idle" ? (
            <AskView tenantId={tenantId} state={askState} />
          ) : (
            <ActiveSearch tenantId={tenantId} query={activeQuery} documentCount={documentCount} />
          )}
        </div>
      )}
    </div>
  );
}

/** The workspace name set in the serif, large over the centred box and
 * small at the start of the top bar. */
function Wordmark({
  tenantName,
  size = "hero",
}: {
  readonly tenantName: string;
  readonly size?: "hero" | "bar";
}) {
  return (
    <h1
      className={cn(
        "font-heading font-semibold tracking-tight text-foreground",
        size === "hero"
          ? "text-center text-4xl break-words"
          : "shrink-0 truncate pt-1 text-xl sm:max-w-48",
      )}
    >
      {tenantName}
    </h1>
  );
}

function SearchBox({
  size,
  initialQuery,
  canAsk,
  isAsking,
  noCreditsMessage,
  onSearch,
  onAsk,
}: {
  readonly size: "hero" | "bar";
  readonly initialQuery: string;
  readonly canAsk: boolean;
  readonly isAsking: boolean;
  readonly noCreditsMessage: string | null;
  readonly onSearch: () => void;
  readonly onAsk: (query: string) => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [value, setValue] = useState(initialQuery);
  const noCreditsId = useId();
  const controlHeight = size === "hero" ? "h-12" : "h-9";

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const query = value.trim();
    if (query === "") return;
    onSearch();
    router.push(
      `${pathname}?${new URLSearchParams({ q: query, type: "search" })}`,
    );
  };

  return (
    <div className="space-y-2">
      <form role="search" onSubmit={submit} className="flex gap-2">
        <Input
          type="search"
          aria-label="Search documents"
          placeholder="Search documents…"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          className={cn(controlHeight, size === "hero" && "px-4 text-base md:text-base")}
        />
        {/* The Query is embedded for each Search, so it runs on submit only. */}
        <Button type="submit" className={cn(controlHeight, "px-4")}>
          Search
        </Button>
        {canAsk && (
          // Disabled while an Answer streams, so a double click never charges
          // twice, and once the Credit Balance is used up.
          <Button
            type="button"
            variant="outline"
            className={cn(controlHeight, "px-4")}
            disabled={isAsking || noCreditsMessage !== null}
            aria-describedby={noCreditsMessage !== null ? noCreditsId : undefined}
            onClick={() => {
              const query = value.trim();
              if (query !== "") onAsk(query);
            }}
          >
            Ask AI
          </Button>
        )}
      </form>
      {noCreditsMessage !== null && (
        <p id={noCreditsId} className="text-sm text-muted-foreground">
          {noCreditsMessage}
        </p>
      )}
    </div>
  );
}

function ActiveSearch({
  tenantId,
  query,
  documentCount,
}: {
  readonly tenantId: string;
  readonly query: string;
  readonly documentCount: number | undefined;
}) {
  const search = useSearch(tenantId, query);
  return (
    <SearchResults
      tenantId={tenantId}
      query={query}
      documentCount={documentCount}
      isPending={search.isFetching && !search.data}
      error={search.error}
      data={search.data}
      onRetry={() => void search.refetch()}
    />
  );
}
