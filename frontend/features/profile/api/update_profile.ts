import { apiFetch } from "@/lib/api_client";

import { profileSchema, type Profile } from "../types";

/** PATCH /users/me/profile: a blank name is sent as null, which the API
 * stores as unset so the email shows instead. */
export async function updateProfile({ name }: { name: string }): Promise<Profile> {
  const data = await apiFetch("/users/me/profile", {
    method: "PATCH",
    credentials: "include",
    body: { name: name === "" ? null : name },
  });
  return profileSchema.parse(data);
}
