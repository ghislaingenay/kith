import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { getSessionIdentity, workspacePath } from "@lib/session_identity";

export default async function Home() {
  let cookie: string | undefined;
  try {
    cookie = (await cookies()).toString();
  } catch {
    cookie = undefined;
  }
  const identity = await getSessionIdentity(cookie ?? "");

  if (!identity) {
    redirect("/sign-in");
  }
  if (identity.memberships.length === 0) {
    redirect("/onboarding");
  }

  redirect(workspacePath(identity.memberships[0].tenant_slug));
}
