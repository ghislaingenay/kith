"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import { Button } from "@/components/ui/button";

// react-pdf needs this set in the module that renders its components.
pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

/** One page of the PDF at `url` at a time, with arrows to step through it.
 * Loaded on the client only: pdf.js needs browser APIs. */
export default function PdfPages({
  url,
  initialPage,
  onFailure,
}: {
  readonly url: string;
  readonly initialPage: number;
  readonly onFailure: () => void;
}) {
  const [pageCount, setPageCount] = useState<number | null>(null);
  const [requestedPage, setRequestedPage] = useState(initialPage);

  // The starting page may be past the end of a shorter file.
  const page =
    pageCount === null ? requestedPage : clamp(requestedPage, pageCount);

  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex items-center justify-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          aria-label="Previous page"
          disabled={page <= 1}
          onClick={() => setRequestedPage(page - 1)}
        >
          <ChevronLeft />
        </Button>
        <span className="font-mono text-xs tabular-nums">
          {pageCount === null ? "Loading…" : `Page ${page} of ${pageCount}`}
        </span>
        <Button
          type="button"
          variant="outline"
          size="icon-sm"
          aria-label="Next page"
          disabled={pageCount === null || page >= pageCount}
          onClick={() => setRequestedPage(page + 1)}
        >
          <ChevronRight />
        </Button>
      </div>
      <div className="min-h-0 overflow-auto rounded-lg border bg-muted">
        <Document
          file={url}
          suspense={false}
          loading={<p className="p-4 text-sm text-muted-foreground">Loading document…</p>}
          error={null}
          onLoadSuccess={({ numPages }) => setPageCount(numPages)}
          onLoadError={onFailure}
        >
          <Page
            pageNumber={page}
            width={640}
            renderTextLayer={false}
            renderAnnotationLayer={false}
            onRenderError={onFailure}
            className="[&_canvas]:h-auto! [&_canvas]:max-w-full"
          />
        </Document>
      </div>
    </div>
  );
}

function clamp(page: number, pageCount: number): number {
  return Math.min(Math.max(page, 1), pageCount);
}
