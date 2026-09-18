import { NextRequest, NextResponse } from "next/server";

import { verifyMagicLinkAndRedirect } from "@/features/verify-magic-link";

/** Lands here from the link in the magic-link email (see
 * MAGIC_LINK_VERIFY_URL) — routing only; see the feature module for the
 * verify/redirect logic. */
export async function GET(request: NextRequest): Promise<NextResponse> {
  return verifyMagicLinkAndRedirect(request);
}
