import { apiFetch } from "@/lib/api_client";

import { profileSchema, type Profile } from "../types";

/** PUT /users/me/avatar: replaces the User's single avatar object. */
export async function uploadAvatar(file: File): Promise<Profile> {
  const body = new FormData();
  body.append("file", file);
  const data = await apiFetch("/users/me/avatar", {
    method: "PUT",
    credentials: "include",
    body,
  });
  return profileSchema.parse(data);
}
