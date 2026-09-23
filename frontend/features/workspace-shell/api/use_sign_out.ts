"use client";

import { useMutation } from "@tanstack/react-query";

import { signOut } from "./sign_out";

export function useSignOut() {
  return useMutation({
    mutationFn: signOut,
  });
}
