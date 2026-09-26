"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import { uploadPdf } from "./upload_pdf";
import { libraryQueryKey } from "./use_library";

export function useUploadPdf(tenantId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadPdf(tenantId, file),
    // The new Document belongs in the library straight away.
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: libraryQueryKey(tenantId) }),
  });
}
