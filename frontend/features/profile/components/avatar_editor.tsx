"use client";

import { ImageUp, Pencil } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

import { useUploadAvatar } from "../api/use_upload_avatar";
import type { Profile } from "../types";
import { displayName } from "../utils/display_name";
import {
  AVATAR_CONTENT_TYPES,
  validateAvatarFile,
} from "../utils/validate_avatar_file";
import { UserAvatar } from "./user_avatar";

const THUMBNAIL_PX = 56;
const PREVIEW_PX = 224;

/** The profile's avatar with an edit affordance: hovering (or focusing) it
 * shows a pencil, and clicking opens a dialog with the image enlarged and a
 * drop zone / file picker to replace it. A chosen file uploads straight
 * away; the new image appears once the API has confirmed it. */
export function AvatarEditor({ profile }: { readonly profile: Profile }) {
  const shownName = displayName(profile);
  const inputRef = useRef<HTMLInputElement>(null);
  const [imageFailed, setImageFailed] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const { mutate, isPending, isSuccess, error, reset } = useUploadAvatar();

  const noImage = !profile.avatar_url || imageFailed;
  const errorMessage = fileError ?? error?.message ?? null;

  const upload = (file: File | null) => {
    if (!file) return;
    reset();
    const problem = validateAvatarFile(file);
    setFileError(problem);
    if (!problem) mutate(file);
  };

  return (
    <Dialog
      onOpenChange={() => {
        reset();
        setFileError(null);
      }}
    >
      <DialogTrigger asChild>
        <button
          type="button"
          aria-label="Change profile photo"
          className="group/edit cursor-pointer relative shrink-0 rounded-full outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <UserAvatar
            displayName={shownName}
            avatarUrl={profile.avatar_url}
            sizePx={THUMBNAIL_PX}
          />
          <span
            aria-hidden="true"
            className="absolute inset-0 flex items-center justify-center rounded-full bg-black/50 text-white opacity-0 transition-opacity group-hover/edit:opacity-100 group-focus-visible/edit:opacity-100"
          >
            <Pencil className="size-4" />
          </span>
        </button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>Profile photo</DialogTitle>
          <DialogDescription>
            Drop a new image below, or choose one from your device.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col items-center gap-2">
          <UserAvatar
            displayName={shownName}
            avatarUrl={profile.avatar_url}
            sizePx={PREVIEW_PX}
            onLoadingStatusChange={(status) =>
              setImageFailed(status === "error")
            }
          />
          {noImage && (
            <p className="text-sm text-muted-foreground">
              No profile photo yet.
            </p>
          )}
        </div>

        <div
          onDragOver={(event) => {
            event.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            upload(event.dataTransfer.files[0] ?? null);
          }}
          className={cn(
            "flex flex-col items-center gap-2 rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground transition-colors",
            dragging && "border-ring bg-muted",
          )}
        >
          <ImageUp className="size-5" aria-hidden="true" />
          <p>Drag an image here, or</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isPending}
            onClick={() => inputRef.current?.click()}
          >
            {isPending ? "Uploading…" : "Choose image"}
          </Button>
          <p id="avatar-hint" className="text-xs">
            JPEG or PNG, up to 2 MB.
          </p>
          <input
            ref={inputRef}
            type="file"
            aria-label="Profile photo file"
            aria-describedby="avatar-hint"
            accept={AVATAR_CONTENT_TYPES.join(",")}
            tabIndex={-1}
            className="sr-only"
            onChange={(event) => {
              upload(event.target.files?.[0] ?? null);
              // So choosing the same file again still fires `change`.
              event.target.value = "";
            }}
          />
        </div>

        {errorMessage && (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage}
          </p>
        )}
        {isSuccess && (
          <p
            role="status"
            className="text-sm text-green-700 dark:text-green-500"
          >
            Photo updated
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
