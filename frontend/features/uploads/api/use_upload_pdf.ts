"use client";

import { useMutation } from "@tanstack/react-query";

import { uploadPdf } from "./upload_pdf";

export function useUploadPdf(tenantId: string) {
  return useMutation({
    mutationFn: (file: File) => uploadPdf(tenantId, file),
  });
}
