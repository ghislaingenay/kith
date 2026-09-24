"use client";

import Link from "next/link";
import { displayName, useProfile, UserAvatar, type Profile } from "@/features/profile";
import { Settings } from "lucide-react";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";

import { SignOutButton } from "./sign_out_button";

export function WorkspaceShell({
  tenantName,
  tenantSlug,
  profile: initialProfile,
  children,
}: {
  readonly tenantName: string;
  readonly tenantSlug: string;
  readonly profile: Profile;
  readonly children: React.ReactNode;
}) {
  const profile = useProfile(initialProfile);
  const shownName = displayName(profile);

  return (
    <SidebarProvider className="flex-1">
      <Sidebar>
        <SidebarHeader>
          <p className="px-2 text-sm font-semibold text-sidebar-foreground">
            {tenantName}
          </p>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <Link href={`/w/${tenantSlug}/settings`}>
                    <Settings /> Settings
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <div className="flex items-center gap-2 px-2 py-1">
            <UserAvatar displayName={shownName} avatarUrl={profile.avatar_url} sizePx={32} />
            <p className="truncate text-sm text-sidebar-foreground">{shownName}</p>
          </div>
          <SignOutButton />
        </SidebarFooter>
      </Sidebar>

      <SidebarInset>
        <header className="flex h-12 shrink-0 items-center border-b border-zinc-200 px-4 dark:border-zinc-800">
          <SidebarTrigger />
        </header>
        <div className="flex flex-1 flex-col">{children}</div>
      </SidebarInset>
    </SidebarProvider>
  );
}
