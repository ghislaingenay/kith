"""Opening an uploaded file as a PDF."""

from pathlib import Path

import pypdfium2
from pypdfium2 import PdfiumError

from documents.exceptions import UnreadablePdfError


def count_pdf_pages(path: Path) -> int:
    """Number of pages in the PDF at `path`. Blocking and CPU-bound: call
    it from a thread."""
    try:
        pdf = pypdfium2.PdfDocument(path)
    except PdfiumError as exc:
        raise UnreadablePdfError("The file could not be opened as a PDF.") from exc
    try:
        return len(pdf)
    finally:
        pdf.close()
