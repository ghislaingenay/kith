export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;

  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-zinc-50 px-4 py-16 dark:bg-black">
      <h1 className="text-xl font-semibold text-zinc-950 dark:text-zinc-50">
        Welcome back
      </h1>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        Your workspace ({slug}) is coming soon.
      </p>
    </div>
  );
}
