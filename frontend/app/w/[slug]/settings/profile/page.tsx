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
        <h1 className="text-xl font-semibold text-zinc-950 dark:text-zinc-50">Settings</h1>
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">Profile</p>
        <div className="mt-6 rounded-xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <ProfileForm profile={profile} />
        </div>
      </div>
    </div>
  );
}
