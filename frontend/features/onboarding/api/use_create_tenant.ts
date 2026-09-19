"use client";

import { useMutation } from "@tanstack/react-query";

import { createTenant } from "./create_tenant";

export function useCreateTenant() {
  return useMutation({
    mutationFn: createTenant,
  });
}
