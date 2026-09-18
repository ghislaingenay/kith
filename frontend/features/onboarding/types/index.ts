import { z } from "zod";

export const workspaceNameSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter a name for your workspace.")
    .max(255, "Keep it under 255 characters."),
});

export type WorkspaceNameInput = Readonly<z.infer<typeof workspaceNameSchema>>;

/** POST /tenants' response (TenantMembershipSummary) — only the field this
 * feature redirects on. */
export const createTenantResponseSchema = z.object({
  tenant_slug: z.string(),
});

export type CreateTenantResponse = Readonly<
  z.infer<typeof createTenantResponseSchema>
>;
