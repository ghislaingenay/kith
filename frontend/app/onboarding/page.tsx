import { OnboardingForm, resolveOnboardingAccess } from "@/features/onboarding";

export default async function OnboardingPage() {
  const { suggestedWorkspaceName } = await resolveOnboardingAccess();

  return (
    <div className="flex flex-1 flex-col items-center justify-center bg-background px-4 py-16">
      <div className="w-full max-w-sm rounded-lg border bg-card p-8">
        <h1 className="text-xl font-semibold text-foreground">
          Name your workspace
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
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
