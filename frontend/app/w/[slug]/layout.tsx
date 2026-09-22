import { resolveWorkspace, WorkspaceShell } from "@/features/workspace-shell";

export default async function WorkspaceLayout({
  children,
  params,
}: LayoutProps<"/w/[slug]">) {
  const { slug } = await params;
  const { tenantName, tenantSlug, profile } = await resolveWorkspace(slug);

  return (
    <WorkspaceShell tenantName={tenantName} tenantSlug={tenantSlug} profile={profile}>
      {children}
    </WorkspaceShell>
  );
}
