import { useEffect, useState, type ReactNode } from "react";

/** Stand-in for `react-pdf` in unit tests (use via `vi.mock("react-pdf", ...)`):
 * jsdom has no canvas or worker. Every PDF has `STUB_PDF_PAGE_COUNT` pages,
 * except a file whose URL contains `broken`, which fails to load. */
export const STUB_PDF_PAGE_COUNT = 3;

export const pdfjs = { GlobalWorkerOptions: { workerSrc: "" } };

export function Document({
  file,
  onLoadSuccess,
  onLoadError,
  children,
}: {
  file: string;
  onLoadSuccess?: (pdf: { numPages: number }) => void;
  onLoadError?: (error: Error) => void;
  children?: ReactNode;
}) {
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (file.includes("broken")) {
      onLoadError?.(new Error("Invalid PDF"));
      return;
    }
    setLoaded(true);
    onLoadSuccess?.({ numPages: STUB_PDF_PAGE_COUNT });
    // The real component loads once per file, whatever the callbacks' identity.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file]);

  return loaded ? <div>{children}</div> : null;
}

export function Page({ pageNumber }: { pageNumber: number }) {
  return <div data-testid="pdf-page">{`PDF page ${pageNumber}`}</div>;
}
