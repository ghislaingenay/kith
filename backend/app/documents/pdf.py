"""Opening an uploaded file as a PDF."""

from pathlib import Path

import pypdfium2
from pypdfium2 import PdfiumError
from pypdfium2.raw import FPDF_ERR_PASSWORD

from documents.exceptions import EncryptedPdfError, UnreadablePdfError


def open_pdf(path: Path) -> pypdfium2.PdfDocument:
    """Open the PDF at `path` for page-by-page extraction. Blocking and
    CPU-bound: call from a thread.

    Unlike `count_pdf_pages`, this doesn't wrap `PdfiumError` into a domain
    exception: by the time ingestion runs, the file already passed upload
    validation (readable, unencrypted), so a failure to open it here isn't
    a page-level extraction failure — it's left to propagate and trigger
    the worker queue's normal retry."""
    return pypdfium2.PdfDocument(path)


def extract_page_text(pdf: pypdfium2.PdfDocument, page_number: int) -> str:
    """Extract page `page_number`'s (1-based) text via `get_text_bounded`,
    the full-Unicode extraction call — `get_text_range`, the other
    extraction call this library exposes, is limited to UCS-2. Blocking
    and CPU-bound: call from a thread.

    Raises if the extraction call itself fails; an empty string is a
    successful call over a page with no text layer, not a failure
    (ADR-0010)."""
    page = pdf[page_number - 1]
    try:
        text_page = page.get_textpage()
        try:
            return text_page.get_text_bounded()
        finally:
            text_page.close()
    finally:
        page.close()


def count_pdf_pages(path: Path) -> int:
    """Number of pages in the PDF at `path`. Blocking and CPU-bound: call
    it from a thread."""
    try:
        pdf = pypdfium2.PdfDocument(path)
    except PdfiumError as exc:
        if exc.err_code == FPDF_ERR_PASSWORD:
            raise EncryptedPdfError(
                "The PDF is password-protected. Remove the password and try again."
            ) from exc
        raise UnreadablePdfError(
            "The PDF could not be read. It may be damaged."
        ) from exc
    try:
        return len(pdf)
    finally:
        pdf.close()
