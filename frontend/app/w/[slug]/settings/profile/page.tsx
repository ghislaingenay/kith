import { ProfileForm } from "@/features/profile";
import { resolveWorkspace } from "@/features/workspace-shell";

export default async function ProfileSettingsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { profile } = await resolveWorkspace(slug);

  return (
    <div className="flex flex-1 flex-col items-center px-4 py-16">
      <div className="w-full max-w-md">
        <h1 className="text-xl font-semibold text-foreground">Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">Profile</p>
        <div className="mt-6 rounded-lg border bg-card p-8">
          <ProfileForm profile={profile} />
        </div>
      </div>
    </div>
  );
}
