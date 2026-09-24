import { env } from "@/config/env";

export class MagicLinkRateLimitError extends Error {}

/** Same request/response shape whether or not `email` has an account
 * (ADR-0006's enumeration guard) — the only distinguishable outcome here is
 * a 429 from the per-email rate limit. */
export async function requestMagicLink(email: string): Promise<void> {
  const response = await fetch(
    `${env.NEXT_PUBLIC_API_URL}/api/v1/auth/magic-link`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    },
  );

  if (response.status === 429) {
    throw new MagicLinkRateLimitError(
      "Too many requests for that email. Try again in a bit.",
    );
  }
  if (!response.ok) {
    throw new Error(
      "Something went wrong sending the magic link. Please try again.",
    );
  }
}
