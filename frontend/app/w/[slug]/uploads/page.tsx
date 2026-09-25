import { UploadScreen } from "@/features/uploads";
import { resolveWorkspace } from "@/features/workspace-shell";

export default async function UploadsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { tenantId } = await resolveWorkspace(slug);

  return <UploadScreen tenantId={tenantId} />;
}
