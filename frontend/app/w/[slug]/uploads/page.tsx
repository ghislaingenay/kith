import { UploadScreen, UploadsLibrary } from "@/features/uploads";
import { resolveWorkspace } from "@/features/workspace-shell";

export default async function UploadsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const { tenantId } = await resolveWorkspace(slug);

  return (
    <div className="flex flex-1 flex-col items-center">
      <UploadScreen tenantId={tenantId} />
      <div className="flex w-full justify-center px-4 pb-16">
        <UploadsLibrary tenantId={tenantId} />
      </div>
    </div>
  );
}
