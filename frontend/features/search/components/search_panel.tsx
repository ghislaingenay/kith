"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useId, useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AskView, useAsk } from "@/features/ask";
import { useCreditBalance } from "@/features/credits";
import { useHasDocuments } from "@/features/uploads";

import { useSearch } from "../api/use_search";
import { SearchResults } from "./search_results";

/** The dashboard's Search box and results. The URL (`?q=…&type=search`) holds
 * the Query, so refresh, Back and shared links all rerun the same Search. An
 * Ask is never in the URL, so a reload never charges again. With the Credit
 * Balance used up, Ask AI is disabled and Search still works (ADR-0017). */
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
  const { hasDocuments, isError } = useHasDocuments(tenantId);
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
      <Alert className="w-full max-w-2xl">
        <AlertTitle>No documents available</AlertTitle>
        <AlertDescription className="space-y-3">
          <p>Upload a document to start searching.</p>
          <Button asChild>
            <Link href={`${pathname}/uploads`}>Go to uploads</Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  const activeQuery =
    params.get("type") === "search" ? (params.get("q") ?? "").trim() : "";

  return (
    <div className="w-full max-w-2xl space-y-6">
      {/* Keyed so Back or a shared link re-fills the box. */}
      <SearchBox
        key={activeQuery}
        initialQuery={activeQuery}
        canAsk={canAsk}
        isAsking={askState.phase === "streaming"}
        noCreditsMessage={noCreditsMessage}
        onSearch={resetAsk}
        onAsk={(query) => void ask(query)}
      />
      {askState.phase !== "idle" ? (
        <AskView tenantId={tenantId} state={askState} />
      ) : (
        activeQuery !== "" && <ActiveSearch tenantId={tenantId} query={activeQuery} />
      )}
    </div>
  );
}

function SearchBox({
  initialQuery,
  canAsk,
  isAsking,
  noCreditsMessage,
  onSearch,
  onAsk,
}: {
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
        />
        {/* The Query is embedded for each Search, so it runs on submit only. */}
        <Button type="submit">Search</Button>
        {canAsk && (
          // Disabled while an Answer streams, so a double click never charges
          // twice, and once the Credit Balance is used up.
          <Button
            type="button"
            variant="outline"
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
}: {
  readonly tenantId: string;
  readonly query: string;
}) {
  const search = useSearch(tenantId, query);
  return (
    <SearchResults
      tenantId={tenantId}
      query={query}
      isPending={search.isFetching && !search.data}
      error={search.error}
      data={search.data}
      onRetry={() => void search.refetch()}
    />
  );
}
