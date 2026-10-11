import { resolveWorkspace, WorkspaceShell } from "@/features/workspace-shell";

export default async function WorkspaceLayout({
  children,
  params,
}: LayoutProps<"/w/[slug]">) {
  const { slug } = await params;
  const { tenantId, tenantName, tenantSlug, role, profile } = await resolveWorkspace(slug);

  return (
    <WorkspaceShell
      tenantId={tenantId}
      tenantName={tenantName}
      tenantSlug={tenantSlug}
      role={role}
      profile={profile}
    >
      {children}
    </WorkspaceShell>
  );
}
