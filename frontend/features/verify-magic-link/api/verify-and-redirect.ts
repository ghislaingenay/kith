import { NextRequest, NextResponse } from "next/server";

import { env } from "@/config/env";
import { getSessionIdentity, workspacePath } from "@/lib/session_identity";

function redirectTo(path: string): NextResponse {
  return NextResponse.redirect(new URL(path, env.APP_URL));
}

/**
 * Verifies a magic-link token server-side, then forwards the session
 * cookie the API just issued into a GET /me call (via the shared
 * `getSessionIdentity`, coding-standards §4.2) to decide where to send the
 * browser — the cookie itself is attached to the redirect response so the
 * browser stores it (ADR-0006: only FastAPI ever sets/clears this cookie,
 * but a Set-Cookie on a server-side fetch response is otherwise dropped, so
 * it's copied across by hand here rather than relying on fetch's cookie
 * jar, which doesn't exist server-side).
 */
export async function verifyMagicLinkAndRedirect(
  request: NextRequest,
): Promise<NextResponse> {
  const token = request.nextUrl.searchParams.get("token");
  const email = request.nextUrl.searchParams.get("email");

  if (!token || !email) {
    return redirectTo("/sign-in?error=invalid-link");
  }

  // only use in server side
  const verifyUrl = new URL(`${env.BACKEND_URL}/api/v1/auth/magic-link/verify`);
  verifyUrl.searchParams.set("token", token);
  verifyUrl.searchParams.set("email", email);

  // Network failure (backend unreachable) is treated like a 5xx below.
  const verifyResponse = await fetch(verifyUrl).catch(() => null);
  if (!verifyResponse) {
    return redirectTo("/sign-in?error=session-failed");
  }
  if (!verifyResponse.ok) {
    // 400 = bad/expired/used token; anything else is an infra failure.
    const errorCode =
      verifyResponse.status === 400 ? "expired-link" : "session-failed";
    return redirectTo(`/sign-in?error=${errorCode}`);
  }

  // Only ever one Set-Cookie here (the session cookie), so `.get` — which
  // joins multiple values with a comma — can't mangle it the way it could
  // for an arbitrary multi-cookie response.
  const setCookieHeader = verifyResponse.headers.get("set-cookie");
  if (!setCookieHeader) {
    return redirectTo("/sign-in?error=session-failed");
  }
  const sessionCookiePair = setCookieHeader.split(";")[0];

  // Right after verifying, any /me failure (invalid session, backend
  // outage) is treated the same way — there's no useful distinction to
  // surface to a visitor who just clicked a fresh link.
  const identity = await getSessionIdentity(sessionCookiePair).catch(
    () => null,
  );
  const destination = identity
    ? destinationFor(identity)
    : "/sign-in?error=session-failed";

  const redirectResponse = redirectTo(destination);
  redirectResponse.headers.set("set-cookie", setCookieHeader);
  return redirectResponse;
}

function destinationFor(identity: {
  memberships: readonly { tenant_slug: string }[];
}): string {
  if (identity.memberships.length === 0) {
    return "/onboarding";
  }
  return workspacePath(identity.memberships[0].tenant_slug);
}
