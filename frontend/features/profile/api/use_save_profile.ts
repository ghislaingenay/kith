"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { profileQueryKey } from "./use_profile";
import { updateProfile } from "./update_profile";

export function useSaveProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: updateProfile,
    onSuccess: (saved) => {
      queryClient.setQueryData(profileQueryKey(saved.email), saved);
    },
  });
}
