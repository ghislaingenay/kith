"use client";

import { useMutation } from "@tanstack/react-query";

import { saveProfile } from "./save_profile";

export function useSaveProfile() {
  return useMutation({
    mutationFn: saveProfile,
  });
}
