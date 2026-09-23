import type { Profile } from "../types";

/** What to call a person in the UI: their name, or their email when unset. */
export function displayName({ name, email }: Pick<Profile, "name" | "email">): string {
  return name ?? email;
}
