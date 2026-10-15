import { Skeleton } from "@/components/ui/skeleton";

/** Shown while a sign-in-style page (or the first entry into a workspace)
 * renders on the server: the same centered card those pages use. */
export function CardPageSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading"
      className="flex flex-1 flex-col items-center justify-center bg-zinc-50 px-4 py-16 dark:bg-black"
    >
      <div className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <Skeleton className="h-6 w-2/3" />
        <Skeleton className="mt-2 h-4 w-full" />
        <Skeleton className="mt-6 h-9 w-full" />
        <Skeleton className="mt-4 h-9 w-full" />
      </div>
    </div>
  );
}

/** Shown in the workspace content area while the next page renders on the
 * server; the sidebar stays in place. */
export function WorkspacePageSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading"
      className="flex flex-1 flex-col items-center px-4 py-16"
    >
      <div className="flex w-full max-w-2xl flex-col items-center">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="mb-8 mt-2 h-4 w-64" />
        <div className="flex w-full flex-col gap-2">
          {ROWS.map((row) => (
            <Skeleton key={row} className="h-16 w-full" />
          ))}
        </div>
      </div>
    </div>
  );
}

const ROWS = [0, 1, 2];
