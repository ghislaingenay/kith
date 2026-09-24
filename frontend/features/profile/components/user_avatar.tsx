"use client";

import { useState, type ComponentProps } from "react";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Skeleton } from "@/components/ui/skeleton";

const SIZE_PX = 40;

type LoadingStatus = Parameters<
  NonNullable<ComponentProps<typeof AvatarImage>["onLoadingStatusChange"]>
>[0];

/** A person's avatar image, or the first letter of their display name when
 * they have none — or when the image can't be loaded (an expired URL, or an
 * object that has since been cleaned up). While the image is still being
 * fetched a pulsing placeholder shows instead, so a slow load never looks
 * like a missing avatar. */
export function UserAvatar({
  displayName,
  avatarUrl,
  sizePx = SIZE_PX,
  onLoadingStatusChange,
}: {
  readonly displayName: string;
  readonly avatarUrl: string | null;
  readonly sizePx?: number;
  readonly onLoadingStatusChange?: (status: LoadingStatus) => void;
}) {
  const [status, setStatus] = useState<LoadingStatus>("idle");

  // `status` is only meaningful while there is a URL to load; "idle" with a
  // URL is the moment before the browser starts fetching it.
  const loading = avatarUrl !== null && status !== "loaded" && status !== "error";

  return (
    <Avatar style={{ width: sizePx, height: sizePx }} aria-busy={loading}>
      {/* Presigned URLs carry their own auth and change on every read, so
          Next's image optimizer (which fetches without them) can't serve
          them — a plain <img> it is. */}
      {avatarUrl && (
        <AvatarImage
          src={avatarUrl}
          alt={displayName}
          onLoadingStatusChange={(next) => {
            setStatus(next);
            onLoadingStatusChange?.(next);
          }}
        />
      )}
      {loading ? (
        <Skeleton aria-hidden="true" className="absolute inset-0 rounded-full" />
      ) : (
        <AvatarFallback
          aria-hidden="true"
          style={{ fontSize: Math.round(sizePx * 0.4) }}
        >
          {displayName.charAt(0).toUpperCase()}
        </AvatarFallback>
      )}
    </Avatar>
  );
}
