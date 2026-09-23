export const MAX_AVATAR_BYTES = 2 * 1024 * 1024;
export const AVATAR_CONTENT_TYPES = ["image/png", "image/jpeg"] as const;

/** Mirrors the API's avatar rules (`users/avatar.py`) so a bad file is
 * refused before it is uploaded. Returns the message to show, or null when
 * the file is fine. */
export function validateAvatarFile(file: File): string | null {
  if (!(AVATAR_CONTENT_TYPES as readonly string[]).includes(file.type)) {
    return "Avatar must be a JPEG or PNG image.";
  }
  if (file.size > MAX_AVATAR_BYTES) {
    return "Avatar image must be 2 MB or smaller.";
  }
  return null;
}
