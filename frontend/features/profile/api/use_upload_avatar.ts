"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { profileQueryKey } from "./use_profile";
import { uploadAvatar } from "./upload_avatar";

export function useUploadAvatar() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: uploadAvatar,
    onSuccess: (saved) => {
      queryClient.setQueryData(profileQueryKey(saved.email), saved);
    },
  });
}
