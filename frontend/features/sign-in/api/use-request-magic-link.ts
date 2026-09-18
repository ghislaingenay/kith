"use client";

import { useMutation } from "@tanstack/react-query";

import { requestMagicLink } from "./request-magic-link";

export function useRequestMagicLink() {
  return useMutation({
    mutationFn: requestMagicLink,
  });
}
