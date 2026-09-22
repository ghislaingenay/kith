import Image from "next/image";

const SIZE_PX = 40;

/** A person's avatar image, or the first letter of their display name when
 * they have none. */
export function UserAvatar({
  displayName,
  avatarUrl,
  sizePx = SIZE_PX,
}: {
  readonly displayName: string;
  readonly avatarUrl: string | null;
  readonly sizePx?: number;
}) {
  if (avatarUrl) {
    return (
      // Presigned URLs carry their own auth and change on every read, so
      // Next's image optimizer (which fetches without them) can't serve them.
      <Image
        src={avatarUrl}
        alt={displayName}
        width={sizePx}
        height={sizePx}
        unoptimized
        className="shrink-0 rounded-full object-cover"
        style={{ width: sizePx, height: sizePx }}
      />
    );
  }

  return (
    <span
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center rounded-full bg-zinc-200 text-sm font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-200"
      style={{ width: sizePx, height: sizePx }}
    >
      {displayName.charAt(0).toUpperCase()}
    </span>
  );
}
