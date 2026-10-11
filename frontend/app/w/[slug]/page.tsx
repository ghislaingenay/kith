import { Suspense } from "react";

import { SearchPanel } from "@/features/search";
import { resolveWorkspace } from "@/features/workspace-shell";

export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { tenantId, tenantName, role } = await resolveWorkspace(slug);

  return (
    <div className="flex flex-1 flex-col items-center px-4 py-16">
      <h1 className="text-xl font-semibold text-zinc-950 dark:text-zinc-50">
        Welcome to {tenantName}
      </h1>
      <p className="mb-8 mt-1 text-sm text-muted-foreground">
        Search your team&apos;s documents.
      </p>
      {/* useSearchParams needs a Suspense boundary to prerender. */}
      <Suspense>
        <SearchPanel tenantId={tenantId} canAsk={role !== "viewer"} />
      </Suspense>
    </div>
  );
}
