"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

import { useDocumentFileUrl } from "../api/use_document_file_url";

// pdf.js needs browser APIs, so it is never rendered on the server.
const PdfPages = dynamic(() => import("./pdf_pages"), {
  ssr: false,
  loading: () => <Status>Loading document…</Status>,
});

/** The real PDF of a Document in a dialog, one page at a time, opening at
 * `initialPage`. Reusable wherever a Document is shown. */
export function DocumentViewerDialog({
  tenantId,
  documentId,
  documentName,
  initialPage = 1,
  open,
  onOpenChange,
}: {
  readonly tenantId: string;
  readonly documentId: string;
  readonly documentName: string;
  readonly initialPage?: number;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
}) {
  const fileUrl = useDocumentFileUrl(tenantId, documentId, open);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);

  const url = fileUrl.data?.url;
  const failed = fileUrl.isError || (url !== undefined && url === failedUrl);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100%-2rem)] grid-rows-[auto_minmax(0,1fr)_auto] sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle className="truncate pr-8">{documentName}</DialogTitle>
          <DialogDescription className="sr-only">
            Preview of {documentName}
          </DialogDescription>
        </DialogHeader>
        {failed ? (
          <p role="alert" className="text-sm text-destructive">
            Could not load the document.
          </p>
        ) : url === undefined ? (
          <Status>Loading document…</Status>
        ) : (
          <PdfPages
            url={url}
            initialPage={initialPage}
            onFailure={() => setFailedUrl(url)}
          />
        )}
        {url !== undefined && !failed && (
          <DialogFooter>
            <Button asChild variant="outline">
              <a href={url} target="_blank" rel="noopener noreferrer">
                Open full document
              </a>
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Status({ children }: { readonly children: string }) {
  return <p className="text-sm text-muted-foreground">{children}</p>;
}
