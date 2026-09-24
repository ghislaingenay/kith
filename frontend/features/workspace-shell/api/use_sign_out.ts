"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { signOut } from "./sign_out";

export function useSignOut() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: signOut,
    // Nothing cached (the Profile, its avatar URL) outlives the session.
    onSuccess: () => queryClient.clear(),
  });
}
