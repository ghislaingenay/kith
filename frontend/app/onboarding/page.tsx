import { OnboardingForm, resolveOnboardingAccess } from "@/features/onboarding";

export default async function OnboardingPage() {
  const { suggestedWorkspaceName } = await resolveOnboardingAccess();

  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-zinc-50 px-4 py-16 dark:bg-black">
      <div className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <h1 className="text-xl font-semibold text-zinc-950 dark:text-zinc-50">
          Name your workspace
        </h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          This is where your team&rsquo;s work will live. You can change the name
          later.
        </p>
        <div className="mt-6">
          <OnboardingForm suggestedWorkspaceName={suggestedWorkspaceName} />
        </div>
      </div>
    </div>
  );
}
