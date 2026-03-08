"""
engine/pdf_reader.py
Extract text from a PDF file.

Optimized with:
  - Parallel page extraction using ThreadPoolExecutor
  - Lower DPI (150) for faster OCR with acceptable accuracy
  - Selective OCR: only OCR pages with no text
  - Page-level fingerprinting for early exit comparison
  - Table extraction support (camelot/tabula fallback)
  - Memory-efficient page-by-page processing

Strategy:
  1. pdfplumber  (best for structured/digital PDFs)
  2. PyMuPDF     (fitz)  — fast, useful fallback
  3. pytesseract — OCR for scanned / image-only PDFs (only empty pages)
  4. Returns None on total failure (→ UNREADABLE)
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── configuration ─────────────────────────────────────────────────────────────
OCR_DPI = 150  # Reduced from 200 for faster processing (still good accuracy)
OCR_MAX_THREADS = min(4, os.cpu_count() or 2)  # Parallel OCR threads per PDF
MIN_TEXT_CHARS = 50  # Minimum chars to consider page as having text


@dataclass
class PageData:
    """Data for a single PDF page."""
    index: int
    text: str
    fingerprint: str
    has_text: bool
    
    
@dataclass
class PDFMetadata:
    """Metadata about a PDF file."""
    path: Path
    file_hash: str
    page_count: int
    is_encrypted: bool
    is_corrupted: bool


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


def _ocr_single_page(args: Tuple) -> Tuple[int, str]:
    """
    OCR a single page. Used for parallel processing.
    Args: (page_index, pdf_path_str, dpi)
    Returns: (page_index, extracted_text)
    """
    page_idx, pdf_path_str, dpi = args
    try:
        import fitz  # noqa: PLC0415
        import pytesseract  # noqa: PLC0415
        from PIL import Image  # noqa: PLC0415
        import io

        doc = fitz.open(pdf_path_str)
        page = doc.load_page(page_idx)
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        text = pytesseract.image_to_string(img, config='--psm 6')  # Assume uniform text block
        doc.close()
        return (page_idx, text)
    except Exception as exc:
        logger.debug("OCR failed for page %d: %s", page_idx, exc)
        return (page_idx, "")


def _extract_with_ocr(pdf_path: Path) -> Optional[str]:
    """
    Convert pages to images and run Tesseract OCR.
    Uses parallel processing for multi-page PDFs.
    """
    try:
        import fitz  # PyMuPDF  # noqa: PLC0415

        doc = fitz.open(str(pdf_path))
        page_count = doc.page_count
        doc.close()

        if page_count == 0:
            return ""

        # Prepare work items
        work_items = [
            (i, str(pdf_path), OCR_DPI)
            for i in range(page_count)
        ]

        # Use threading for I/O-bound OCR work
        if page_count > 1 and OCR_MAX_THREADS > 1:
            with ThreadPoolExecutor(max_workers=min(OCR_MAX_THREADS, page_count)) as executor:
                results = list(executor.map(_ocr_single_page, work_items))
        else:
            results = [_ocr_single_page(item) for item in work_items]

        # Sort by page index and join
        results.sort(key=lambda x: x[0])
        pages_text = [text for _, text in results]
        return "\n".join(pages_text)

    except Exception as exc:
        logger.debug("OCR failed for %s: %s", pdf_path, exc)
        return None


def _extract_with_selective_ocr(pdf_path: Path, existing_texts: List[str]) -> Optional[str]:
    """
    Only OCR pages that have no/minimal text.
    This dramatically speeds up mixed PDFs (some digital, some scanned).
    """
    try:
        import fitz  # noqa: PLC0415

        doc = fitz.open(str(pdf_path))
        page_count = doc.page_count
        doc.close()

        # Find pages that need OCR (empty or nearly empty)
        pages_needing_ocr = []
        for i, text in enumerate(existing_texts):
            if len(text.strip()) < 50:  # Less than 50 chars = likely needs OCR
                pages_needing_ocr.append(i)

        if not pages_needing_ocr:
            # No OCR needed
            return "\n".join(existing_texts)

        logger.debug("Selective OCR: %d/%d pages need OCR for %s",
                     len(pages_needing_ocr), page_count, pdf_path.name)

        # OCR only the empty pages
        work_items = [
            (i, str(pdf_path), OCR_DPI)
            for i in pages_needing_ocr
        ]

        if len(work_items) > 1 and OCR_MAX_THREADS > 1:
            with ThreadPoolExecutor(max_workers=min(OCR_MAX_THREADS, len(work_items))) as executor:
                results = list(executor.map(_ocr_single_page, work_items))
        else:
            results = [_ocr_single_page(item) for item in work_items]

        # Merge OCR results back into existing texts
        ocr_map = {idx: text for idx, text in results}
        final_texts = []
        for i, text in enumerate(existing_texts):
            if i in ocr_map and len(text.strip()) < 50:
                final_texts.append(ocr_map[i])
            else:
                final_texts.append(text)

        return "\n".join(final_texts)

    except Exception as exc:
        logger.debug("Selective OCR failed for %s: %s", pdf_path, exc)
        return None


# ---------------------------------------------------------------------------
# File hash and metadata functions
# ---------------------------------------------------------------------------

def compute_file_hash(pdf_path: Path, chunk_size: int = 65536) -> str:
    """
    Compute MD5 hash of a PDF file.
    Uses chunked reading for memory efficiency with large files.
    """
    md5 = hashlib.md5()
    try:
        with open(pdf_path, 'rb') as f:
            while chunk := f.read(chunk_size):
                md5.update(chunk)
        return md5.hexdigest()
    except Exception as exc:
        logger.debug("Failed to compute hash for %s: %s", pdf_path, exc)
        return ""


def get_pdf_metadata(pdf_path: Path) -> PDFMetadata:
    """
    Get metadata about a PDF file including hash, page count, encryption status.
    """
    pdf_path = Path(pdf_path)
    
    # Default values for corrupted/missing files
    file_hash = ""
    page_count = -1
    is_encrypted = False
    is_corrupted = False
    
    if not pdf_path.exists():
        is_corrupted = True
        return PDFMetadata(
            path=pdf_path,
            file_hash=file_hash,
            page_count=page_count,
            is_encrypted=is_encrypted,
            is_corrupted=True
        )
    
    # Compute file hash
    file_hash = compute_file_hash(pdf_path)
    
    # Get page count and check for encryption/corruption
    try:
        import fitz  # noqa: PLC0415
        
        doc = fitz.open(str(pdf_path))
        is_encrypted = doc.is_encrypted
        
        if is_encrypted and not doc.authenticate(""):
            # Encrypted and we can't open it
            page_count = -1
        else:
            page_count = doc.page_count
        
        doc.close()
        
    except Exception as exc:
        logger.debug("Failed to read PDF metadata for %s: %s", pdf_path, exc)
        is_corrupted = True
    
    return PDFMetadata(
        path=pdf_path,
        file_hash=file_hash,
        page_count=page_count,
        is_encrypted=is_encrypted,
        is_corrupted=is_corrupted
    )


# ---------------------------------------------------------------------------
# Page-level extraction with fingerprinting
# ---------------------------------------------------------------------------

def _compute_text_fingerprint(text: str) -> str:
    """Compute MD5 fingerprint of normalized text."""
    from utils.text_normalizer import text_to_fingerprint
    return text_to_fingerprint(text)


def extract_page_text(pdf_path: Path, page_index: int) -> Tuple[str, bool]:
    """
    Extract text from a single page. Memory-efficient single-page extraction.
    
    Returns:
        (text, needs_ocr) - text content and whether OCR might be needed
    """
    try:
        import fitz  # noqa: PLC0415
        
        doc = fitz.open(str(pdf_path))
        if page_index >= doc.page_count:
            doc.close()
            return ("", False)
        
        page = doc.load_page(page_index)
        text = page.get_text()
        doc.close()  # Release memory immediately
        
        needs_ocr = len(text.strip()) < MIN_TEXT_CHARS
        return (text, needs_ocr)
        
    except Exception as exc:
        logger.debug("Failed to extract page %d from %s: %s", page_index, pdf_path, exc)
        return ("", True)


def extract_page_with_ocr(pdf_path: Path, page_index: int) -> str:
    """
    Extract text from a single page, using OCR if needed.
    """
    text, needs_ocr = extract_page_text(pdf_path, page_index)
    
    if needs_ocr:
        # Try OCR for this page
        result = _ocr_single_page((page_index, str(pdf_path), OCR_DPI))
        return result[1] if result else text
    
    return text


def iter_pages_with_fingerprints(
    pdf_path: Path,
    use_ocr: bool = True
) -> Generator[PageData, None, None]:
    """
    Memory-efficient generator that yields PageData for each page.
    Processes one page at a time to minimize memory usage.
    
    Yields:
        PageData objects with text and fingerprint for each page
    """
    from utils.text_normalizer import text_to_fingerprint
    
    try:
        import fitz  # noqa: PLC0415
        
        doc = fitz.open(str(pdf_path))
        page_count = doc.page_count
        doc.close()
        
        for i in range(page_count):
            if use_ocr:
                text = extract_page_with_ocr(pdf_path, i)
            else:
                text, _ = extract_page_text(pdf_path, i)
            
            fingerprint = text_to_fingerprint(text)
            has_text = len(text.strip()) >= MIN_TEXT_CHARS
            
            yield PageData(
                index=i,
                text=text,
                fingerprint=fingerprint,
                has_text=has_text
            )
            
    except Exception as exc:
        logger.error("Failed to iterate pages for %s: %s", pdf_path, exc)


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------

def extract_tables_from_page(pdf_path: Path, page_index: int) -> List[List[List[str]]]:
    """
    Extract tables from a specific page using camelot or tabula.
    Returns list of tables, each table is a list of rows, each row is a list of cells.
    """
    tables = []
    
    # Try camelot first (better accuracy for bordered tables)
    try:
        import camelot  # noqa: PLC0415
        
        # camelot uses 1-based page indexing
        camelot_tables = camelot.read_pdf(
            str(pdf_path),
            pages=str(page_index + 1),
            flavor='lattice'  # For bordered tables
        )
        
        for table in camelot_tables:
            tables.append(table.df.values.tolist())
        
        if tables:
            return tables
            
    except ImportError:
        logger.debug("camelot not available, trying tabula")
    except Exception as exc:
        logger.debug("camelot failed for page %d of %s: %s", page_index, pdf_path, exc)
    
    # Fallback to tabula
    try:
        import tabula  # noqa: PLC0415
        
        # tabula uses 1-based page indexing
        tabula_tables = tabula.read_pdf(
            str(pdf_path),
            pages=page_index + 1,
            multiple_tables=True
        )
        
        for df in tabula_tables:
            if df is not None and not df.empty:
                tables.append(df.fillna('').values.tolist())
                
    except ImportError:
        logger.debug("tabula not available")
    except Exception as exc:
        logger.debug("tabula failed for page %d of %s: %s", page_index, pdf_path, exc)
    
    return tables


def extract_page_with_tables(pdf_path: Path, page_index: int) -> str:
    """
    Extract text from a page, including flattened table content.
    """
    from utils.text_normalizer import normalize_table_text
    
    # Get regular text
    text = extract_page_with_ocr(pdf_path, page_index)
    
    # Try to extract tables
    try:
        tables = extract_tables_from_page(pdf_path, page_index)
        if tables:
            table_texts = [normalize_table_text(table) for table in tables]
            # Append table content to page text
            text = text + " " + " ".join(table_texts)
    except Exception as exc:
        logger.debug("Table extraction failed for page %d: %s", page_index, exc)
    
    return text


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


def _extract_page_texts_pymupdf(pdf_path: Path) -> Optional[List[str]]:
    """Extract text per page using PyMuPDF. Returns list of page texts."""
    try:
        import fitz  # noqa: PLC0415
        doc = fitz.open(str(pdf_path))
        page_texts = [page.get_text() for page in doc]
        doc.close()
        return page_texts
    except Exception:
        return None


def extract_text(pdf_path: Path) -> Optional[str]:
    """
    Extract plain text from a PDF.
    
    Optimized strategy:
      1. Try pdfplumber (best for digital PDFs)
      2. Try PyMuPDF 
      3. Use selective OCR (only OCR pages with no/minimal text)

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

    # --- attempt 2: PyMuPDF (with page-level text for selective OCR) ---
    page_texts = _extract_page_texts_pymupdf(pdf_path)
    if page_texts is not None:
        full_text = "\n".join(page_texts)
        if full_text.strip():
            logger.debug("PyMuPDF succeeded for %s", pdf_path.name)
            return full_text
        
        # Check if any pages have text - if not, need full OCR
        has_any_text = any(pt.strip() for pt in page_texts)
        
        if has_any_text:
            # Some pages have text, some don't - use selective OCR
            logger.info("%s has mixed content; using selective OCR …", pdf_path.name)
            text = _extract_with_selective_ocr(pdf_path, page_texts)
            if text is not None:
                logger.debug("Selective OCR finished for %s", pdf_path.name)
                return text

    # All digital extraction returned empty — likely fully scanned PDF
    logger.info("%s returned no text; attempting full OCR …", pdf_path.name)

    # --- attempt 3: Full OCR ---
    text = _extract_with_ocr(pdf_path)
    if text is not None:
        logger.debug("Full OCR finished for %s", pdf_path.name)
        return text  # could still be empty string for truly blank page

    # All strategies failed
    logger.warning("All extraction strategies failed for %s", pdf_path.name)
    return None
