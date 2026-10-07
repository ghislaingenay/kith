"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Input } from "@/components/ui/input";

import { useSearch } from "../api/use_search";
import { SearchResults } from "./search_results";

/** The dashboard's Search box and results. The URL (`?q=…&type=search`) holds
 * the Query, so refresh, Back and shared links all rerun the same Search. */
export function SearchPanel({ tenantId }: { readonly tenantId: string }) {
  const params = useSearchParams();
  const activeQuery =
    params.get("type") === "search" ? (params.get("q") ?? "").trim() : "";

  return (
    <div className="w-full max-w-2xl space-y-6">
      {/* Keyed so Back or a shared link re-fills the box. */}
      <SearchBox key={activeQuery} initialQuery={activeQuery} />
      {activeQuery !== "" && (
        <ActiveSearch tenantId={tenantId} query={activeQuery} />
      )}
    </div>
  );
}

function SearchBox({ initialQuery }: { readonly initialQuery: string }) {
  const router = useRouter();
  const pathname = usePathname();
  const [value, setValue] = useState(initialQuery);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const query = value.trim();
    if (query === "") return;
    router.push(`${pathname}?${new URLSearchParams({ q: query, type: "search" })}`);
  };

  return (
    <form role="search" onSubmit={submit}>
      <Input
        type="search"
        aria-label="Search documents"
        placeholder="Search documents…"
        value={value}
        onChange={(event) => setValue(event.target.value)}
      />
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
      query={query}
      isPending={search.isFetching && !search.data}
      error={search.error}
      data={search.data}
      onRetry={() => void search.refetch()}
    />
  );
}
