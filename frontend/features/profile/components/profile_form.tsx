"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { useProfile } from "../api/use_profile";
import { useSaveProfile } from "../api/use_save_profile";
import {
  profileFormSchema,
  type Profile,
  type ProfileFormInput,
} from "../types";
import { displayName } from "../utils/display_name";
import { AvatarEditor } from "./avatar_editor";

export function ProfileForm({ profile: initialProfile }: { readonly profile: Profile }) {
  // The shared cache entry, so a save here (or an avatar change) shows up in
  // the workspace sidebar too. The prop only seeds it: it is a server-render
  // snapshot and never changes after a save.
  const profile = useProfile(initialProfile);
  const { mutate, isPending, isSuccess, error, reset } = useSaveProfile();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<ProfileFormInput>({
    resolver: zodResolver(profileFormSchema),
    defaultValues: { name: profile.name ?? "" },
  });

  const onSubmit = handleSubmit(({ name }) => mutate({ name }));

  const shownName = displayName(profile);

  return (
    <form onSubmit={onSubmit} className="flex w-full flex-col gap-6" noValidate>
      <div className="flex items-center gap-3">
        <AvatarEditor profile={profile} />
        <h2 className="text-base font-medium text-zinc-950 dark:text-zinc-50">
          {shownName}
        </h2>
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
