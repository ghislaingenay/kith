"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AskView, useAsk } from "@/features/ask";
import { useHasDocuments } from "@/features/uploads";

import { useSearch } from "../api/use_search";
import { SearchResults } from "./search_results";

/** The dashboard's Search box and results. The URL (`?q=…&type=search`) holds
 * the Query, so refresh, Back and shared links all rerun the same Search. An
 * Ask is never in the URL, so a reload never charges again. */
export function SearchPanel({
  tenantId,
  canAsk,
}: {
  readonly tenantId: string;
  readonly canAsk: boolean;
}) {
  const params = useSearchParams();
  const pathname = usePathname();
  const { hasDocuments, isError } = useHasDocuments(tenantId);
  const { state: askState, ask, reset: resetAsk } = useAsk(tenantId);

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
  onSearch,
  onAsk,
}: {
  readonly initialQuery: string;
  readonly canAsk: boolean;
  readonly isAsking: boolean;
  readonly onSearch: () => void;
  readonly onAsk: (query: string) => void;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [value, setValue] = useState(initialQuery);

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
        // Disabled while an Answer streams, so a double click never charges twice.
        <Button
          type="button"
          variant="outline"
          disabled={isAsking}
          onClick={() => {
            const query = value.trim();
            if (query !== "") onAsk(query);
          }}
        >
          Ask AI
        </Button>
      )}
    </form>
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
