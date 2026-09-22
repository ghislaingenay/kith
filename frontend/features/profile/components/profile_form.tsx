"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useForm } from "react-hook-form";

import { useSaveProfile } from "../api/use_save_profile";
import { profileFormSchema, type Profile, type ProfileFormInput } from "../types";
import { displayName } from "../utils/display_name";
import { AVATAR_CONTENT_TYPES, validateAvatarFile } from "../utils/validate_avatar_file";
import { UserAvatar } from "./user_avatar";

export function ProfileForm({ profile: initialProfile }: { readonly profile: Profile }) {
  const router = useRouter();
  const [profile, setProfile] = useState(initialProfile);
  const { mutate, isPending, isSuccess, error, reset } = useSaveProfile();
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ProfileFormInput>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: { name: profile.name ?? "" },
  });

  const onAvatarChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    setAvatarFile(file);
    setAvatarError(file ? validateAvatarFile(file) : null);
    reset();
  };

  const onSubmit = handleSubmit(({ name }) => {
    if (avatarError) return;
    mutate(
      { name, avatar: avatarFile },
      {
        onSuccess: (saved) => {
          setProfile(saved);
          setAvatarFile(null);
          if (fileInputRef.current) fileInputRef.current.value = "";
          // The shell is a layout, which doesn't re-render on its own.
          router.refresh();
        },
      },
    );
  });

  const shownName = displayName(profile);

  return (
    <form onSubmit={onSubmit} className="flex w-full flex-col gap-6" noValidate>
      <div className="flex items-center gap-3">
        {/* Never a local preview: the picked file isn't confirmed saved
            until the server returns the new avatar_url. */}
        <UserAvatar displayName={shownName} avatarUrl={profile.avatar_url} sizePx={56} />
        <h2 className="text-base font-medium text-zinc-950 dark:text-zinc-50">
          {shownName}
        </h2>
      </div>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="avatar"
          className="text-sm font-medium text-zinc-950 dark:text-zinc-50"
        >
          Avatar
        </label>
        <input
          id="avatar"
          ref={fileInputRef}
          type="file"
          accept={AVATAR_CONTENT_TYPES.join(",")}
          aria-invalid={avatarError ? "true" : "false"}
          aria-describedby={avatarError ? "avatar-error" : "avatar-hint"}
          onChange={onAvatarChange}
          className="text-sm text-zinc-600 dark:text-zinc-400"
        />
        <p id="avatar-hint" className="text-xs text-zinc-500">
          JPEG or PNG, up to 2 MB.
        </p>
        {avatarError && (
          <p id="avatar-error" role="alert" className="text-sm text-red-600">
            {avatarError}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <label
          htmlFor="name"
          className="text-sm font-medium text-zinc-950 dark:text-zinc-50"
        >
          Name
        </label>
        <input
          id="name"
          type="text"
          autoComplete="name"
          placeholder={profile.email}
          aria-invalid={errors.name ? "true" : "false"}
          aria-describedby={errors.name ? "name-error" : undefined}
          className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-950 dark:border-zinc-700 dark:bg-black dark:text-zinc-50"
          {...register("name", { onChange: () => reset() })}
        />
        {errors.name && (
          <p id="name-error" role="alert" className="text-sm text-red-600">
            {errors.name.message}
          </p>
        )}
      </div>

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error.message}
        </p>
      )}
      {isSuccess && (
        <p role="status" className="text-sm text-green-700 dark:text-green-500">
          Profile saved
        </p>
      )}

      <button
        type="submit"
        disabled={isPending}
        className="self-start rounded-full bg-foreground px-5 py-2.5 text-sm font-medium text-background transition-colors hover:bg-[#383838] disabled:opacity-50 dark:hover:bg-[#ccc]"
      >
        {isPending ? "Saving…" : "Save"}
      </button>
    </form>
  );
}
