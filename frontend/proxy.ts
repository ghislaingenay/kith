import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME } from "@/lib/session_identity";

/**
 * Centralized route protection (coding-standards §4.2): a single
 * project-root entrypoint, rather than each route checking for itself.
 *
 * This only checks that the session cookie is *present* — cheap, and safe
 * to do on every matched request without hitting the backend. It does not
 * validate the session; an expired or revoked one still passes here and is
 * caught by the page's own GET /me call (see `lib/session_identity.ts`),
 * which is the only place that can actually ask the backend whether a
 * session is still good.
 */
export function proxy(request: NextRequest): NextResponse {
  if (!request.cookies.has(SESSION_COOKIE_NAME)) {
    return NextResponse.redirect(new URL("/sign-in", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/onboarding", "/w/:path*"],
};
