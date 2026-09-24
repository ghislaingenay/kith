"use client";

import { useQuery } from "@tanstack/react-query";

import type { Profile } from "../types";
import { fetchProfile } from "./fetch_profile";

// The API presigns avatar URLs for 4 h (`AVATAR_PRESIGNED_URL_TTL_SECONDS`);
// refetching well inside that keeps the cached URL from expiring on screen.
const PROFILE_STALE_MS = 30 * 60 * 1000;

/** Keyed by email so one person's cached Profile can never be shown to the
 * next person who signs in on the same tab. */
export const profileQueryKey = (email: string) => ["profile", email] as const;

/** The signed-in person's Profile, shared by every component that shows it.
 * The server-rendered `/me` profile seeds the cache, so the first render
 * needs no request; saves write straight into it (see `useSaveProfile`,
 * `useUploadAvatar`), so the sidebar and the settings page never disagree. */
export function useProfile(initialProfile: Profile): Profile {
  const { data } = useQuery({
    queryKey: profileQueryKey(initialProfile.email),
    queryFn: fetchProfile,
    initialData: initialProfile,
    staleTime: PROFILE_STALE_MS,
  });
  return data;
}
