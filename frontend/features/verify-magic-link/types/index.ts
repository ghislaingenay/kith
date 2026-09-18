import { z } from "zod";

/** The bit of GET /me's response this feature needs to decide a redirect. */
export const meResponseSchema = z.object({
  memberships: z.array(
    z.object({
      tenant_slug: z.string(),
    }),
  ),
});

export type MeResponse = Readonly<z.infer<typeof meResponseSchema>>;
