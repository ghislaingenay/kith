import { z } from "zod";

import { apiFetch } from "@/lib/api_client";

import { profileSchema, type Profile } from "../types";

// `/me` is the profile's one source: the server-rendered shell reads it via
// `getSessionIdentity`, and this is the same call made from the browser.
const meProfileSchema = z.object({ profile: profileSchema });

/** GET /me from the browser, keeping only the Profile — its avatar URL is
 * freshly presigned on every call. */
export async function fetchProfile(): Promise<Profile> {
  const data = await apiFetch("/api/v1/me", { credentials: "include" });
  return meProfileSchema.parse(data).profile;
}
