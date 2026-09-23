import { NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE_NAME } from "@lib/session_identity";

export function proxy(request: NextRequest): NextResponse {
  if (!request.cookies.has(SESSION_COOKIE_NAME)) {
    return NextResponse.redirect(new URL("/sign-in", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/onboarding", "/w/:path*"],
};
