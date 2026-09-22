import { z } from "zod";

/** The caller's Profile as `GET /me` and `/users/me/*` return it. `name` and
 * `avatar_url` are null until set; `avatar_url` is a presigned URL that
 * expires, so it is never stored. */
export const profileSchema = z.object({
  email: z.string().email(),
  name: z.string().nullable(),
  avatar_url: z.string().nullable(),
});

export type Profile = Readonly<z.infer<typeof profileSchema>>;

export const profileFormSchema = z.object({
  name: z.string().trim().max(100, "Keep it under 100 characters."),
});

export type ProfileFormInput = Readonly<z.infer<typeof profileFormSchema>>;
