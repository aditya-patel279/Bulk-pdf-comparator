"""
engine/pdf_reader.py
Extract text from a PDF file.

Strategy:
  1. pdfplumber  (best for structured/digital PDFs)
  2. PyMuPDF     (fitz)  — fast, useful fallback
  3. pytesseract — OCR for scanned / image-only PDFs
  4. Returns None on total failure (→ UNREADABLE)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _extract_with_pdfplumber(pdf_path: Path) -> Optional[str]:
    try:
        import pdfplumber  # noqa: PLC0415

        with pdfplumber.open(str(pdf_path)) as pdf:
            pages_text = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text)
            return "\n".join(pages_text)
    except Exception as exc:
        logger.debug("pdfplumber failed for %s: %s", pdf_path, exc)
        return None


def _extract_with_pymupdf(pdf_path: Path) -> Optional[str]:
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415

        doc = fitz.open(str(pdf_path))
        pages_text = [page.get_text() for page in doc]
        doc.close()
        return "\n".join(pages_text)
    except Exception as exc:
        logger.debug("PyMuPDF failed for %s: %s", pdf_path, exc)
        return None


def _extract_with_ocr(pdf_path: Path) -> Optional[str]:
    """Convert each page to an image and run Tesseract OCR."""
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415
        import pytesseract  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415
        import io

        doc = fitz.open(str(pdf_path))
        pages_text = []
        for page in doc:
            # Render at 200 DPI for reasonable OCR accuracy
            mat = fitz.Matrix(200 / 72, 200 / 72)
            pix = page.get_pixmap(matrix=mat)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            text = pytesseract.image_to_string(img)
            pages_text.append(text)
        doc.close()
        return "\n".join(pages_text)
    except Exception as exc:
        logger.debug("OCR failed for %s: %s", pdf_path, exc)
        return None


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

def get_page_count(pdf_path: Path) -> int:
    """Return page count, or -1 on error."""
    try:
        import fitz  # noqa: PLC0415

        doc = fitz.open(str(pdf_path))
        count = doc.page_count
        doc.close()
        return count
    except Exception:
        return -1


def extract_text(pdf_path: Path) -> Optional[str]:
    """
    Extract plain text from a PDF.

    Returns:
        str  — extracted text (may be empty for blank documents)
        None — file is unreadable / corrupted
    """
    pdf_path = Path(pdf_path)

    if not pdf_path.exists():
        return None

    # --- attempt 1: pdfplumber ---
    text = _extract_with_pdfplumber(pdf_path)
    if text and text.strip():
        logger.debug("pdfplumber succeeded for %s", pdf_path.name)
        return text

    # --- attempt 2: PyMuPDF ---
    text = _extract_with_pymupdf(pdf_path)
    if text and text.strip():
        logger.debug("PyMuPDF succeeded for %s", pdf_path.name)
        return text

    # Both returned empty — may be a scanned / image PDF
    logger.info("%s returned no text; attempting OCR …", pdf_path.name)

    # --- attempt 3: OCR ---
    text = _extract_with_ocr(pdf_path)
    if text is not None:
        logger.debug("OCR finished for %s", pdf_path.name)
        return text  # could still be empty string for truly blank page

    # All strategies failed
    logger.warning("All extraction strategies failed for %s", pdf_path.name)
    return None
