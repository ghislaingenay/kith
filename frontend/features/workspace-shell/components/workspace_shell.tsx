"use client";

import Link from "next/link";
import { displayName, UserAvatar, type Profile } from "@/features/profile";

import { SignOutButton } from "./sign_out_button";

export function WorkspaceShell({
  tenantName,
  tenantSlug,
  profile,
  children,
}: {
  readonly tenantName: string;
  readonly tenantSlug: string;
  readonly profile: Profile;
  readonly children: React.ReactNode;
}) {
  const shownName = displayName(profile);

  return (
    <div className="flex flex-1 bg-zinc-50 dark:bg-black">
      <aside className="flex w-60 shrink-0 flex-col justify-between border-r border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-col gap-4">
          <p className="px-3 text-sm font-semibold text-zinc-950 dark:text-zinc-50">
            {tenantName}
          </p>
          <nav aria-label="Workspace">
            <Link
              href={`/w/${tenantSlug}/settings`}
              className="block rounded-md px-3 py-2 text-sm text-zinc-700 transition-colors hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-900"
            >
              Settings
            </Link>
          </nav>
        </div>

        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-2 px-3">
            <UserAvatar displayName={shownName} avatarUrl={profile.avatar_url} sizePx={32} />
            <p className="truncate text-sm text-zinc-950 dark:text-zinc-50">{shownName}</p>
          </div>
          <SignOutButton />
        </div>
      </aside>

      <main className="flex flex-1 flex-col">{children}</main>
    </div>
  );
}
