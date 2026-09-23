import { resolveWorkspace } from "@/features/workspace-shell";

export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { tenantName } = await resolveWorkspace(slug);

  return (
    <div className="flex flex-1 flex-col items-center justify-center px-4 py-16">
      <h1 className="text-xl font-semibold text-zinc-950 dark:text-zinc-50">
        Welcome to {tenantName}
      </h1>
    </div>
  );
}
