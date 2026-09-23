import type { Profile } from "../types";
import { updateProfile } from "./update_profile";
import { uploadAvatar } from "./upload_avatar";

/** Saves what the form holds: the avatar first (if a new one was chosen), so
 * a failed upload leaves the name untouched, then the name. The name call's
 * response is the whole Profile, including the new avatar's fresh URL. */
export async function saveProfile({
  name,
  avatar,
}: {
  name: string;
  avatar: File | null;
}): Promise<Profile> {
  if (avatar) {
    await uploadAvatar(avatar);
  }
  return updateProfile({ name });
}
