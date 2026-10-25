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
    <div className="flex flex-1 flex-col">
      {/* useSearchParams needs a Suspense boundary to prerender. */}
      <Suspense>
        <SearchPanel
          tenantId={tenantId}
          tenantName={tenantName}
          canAsk={role !== "viewer"}
        />
      </Suspense>
    </div>
  );
}
