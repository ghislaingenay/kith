"use client";

import { FileText } from "lucide-react";
import { useRef, useState } from "react";

import { Button } from "@/components/ui/button";

import { useUploadPdf } from "../api/use_upload_pdf";
import { PDF_CONTENT_TYPE, validatePdfFile } from "../utils/validate_pdf_file";

/** The upload screen: pick a PDF and see whether it was accepted. The API
 * checks the file again after it arrives; this only spares an obviously bad
 * file the trip. */
export function UploadScreen({ tenantId }: { readonly tenantId: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [chosen, setChosen] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const { mutate, isPending, isSuccess, error, reset } = useUploadPdf(tenantId);

  const errorMessage = fileError ?? error?.message ?? null;

  const choose = (file: File | null) => {
    if (!file) return;
    reset();
    setChosen(file);
    const problem = validatePdfFile(file);
    setFileError(problem);
    if (!problem) mutate(file);
  };

  return (
    <div className="flex flex-1 flex-col items-center px-4 py-16">
      <div className="w-full max-w-xl">
        <h1 className="text-xl font-semibold text-zinc-950 dark:text-zinc-50">
          Upload
        </h1>

        <div className="mt-6 flex flex-col items-center gap-2 rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          <FileText className="size-6" aria-hidden="true" />
          <p>PDF, up to 20 MB</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isPending}
            onClick={() => inputRef.current?.click()}
          >
            Select Files
          </Button>
          <input
            ref={inputRef}
            type="file"
            aria-label="PDF file"
            accept={PDF_CONTENT_TYPE}
            tabIndex={-1}
            className="sr-only"
            onChange={(event) => {
              choose(event.target.files?.[0] ?? null);
              // So choosing the same file again still fires `change`.
              event.target.value = "";
            }}
          />
        </div>

        {chosen && (
          <ul className="mt-4 divide-y rounded-lg border text-sm">
            <li className="flex flex-col gap-1 px-4 py-3">
              <div className="flex items-center justify-between gap-4">
                <span className="truncate">{chosen.name}</span>
                {isPending && <span role="status">Uploading…</span>}
                {isSuccess && (
                  <span role="status" className="text-green-700 dark:text-green-500">
                    Accepted
                  </span>
                )}
              </div>
              {errorMessage && (
                <p role="alert" className="text-destructive">
                  {errorMessage}
                </p>
              )}
            </li>
          </ul>
        )}
      </div>
    </div>
  );
}
