"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { displayName, useProfile, UserAvatar, type Profile } from "@/features/profile";
import { Building2, Home, Settings, Upload } from "lucide-react";

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
  const pathname = usePathname();
  const homeHref = `/w/${tenantSlug}`;
  const uploadsHref = `/w/${tenantSlug}/uploads`;
  const settingsHref = `/w/${tenantSlug}/settings`;

  return (
    <SidebarProvider className="flex-1">
      <Sidebar collapsible="icon">
        <SidebarHeader>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton size="lg" className="cursor-default hover:bg-transparent">
                <div className="flex aspect-square size-8 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                  <Building2 className="size-4" />
                </div>
                <span className="truncate font-semibold text-sidebar-foreground">
                  {tenantName}
                </span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={pathname === homeHref}>
                  <Link href={homeHref}>
                    <Home /> Home
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={pathname.startsWith(uploadsHref)}>
                  <Link href={uploadsHref}>
                    <Upload /> Uploads
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton asChild isActive={pathname.startsWith(settingsHref)}>
                  <Link href={settingsHref}>
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
