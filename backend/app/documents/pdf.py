"""Opening an uploaded file as a PDF."""

from pathlib import Path

import pypdfium2
from pypdfium2 import PdfiumError
from pypdfium2.raw import FPDF_ERR_PASSWORD

from documents.exceptions import EncryptedPdfError, UnreadablePdfError


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
