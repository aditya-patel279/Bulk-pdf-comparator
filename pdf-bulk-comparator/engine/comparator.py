"""
engine/comparator.py
Compare a single old/new PDF pair and return a result dict.
"""

from __future__ import annotations

import difflib
import logging
from pathlib import Path
from typing import Optional

from engine.pdf_reader import extract_text, get_page_count
from utils.text_normalizer import normalize

logger = logging.getLogger(__name__)

# ── similarity threshold ─────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.99

# ── status constants ─────────────────────────────────────────────────────────
STATUS_SAME             = "SAME"
STATUS_CHANGED          = "CHANGED"
STATUS_MISSING_NEW      = "MISSING_NEW_FILE"
STATUS_MISSING_OLD      = "MISSING_OLD_FILE"
STATUS_UNREADABLE       = "UNREADABLE"
STATUS_MISSING_BOTH     = "MISSING_BOTH"


def _similarity(text_a: str, text_b: str) -> float:
    """Fast SequenceMatcher ratio between two normalised strings."""
    if not text_a and not text_b:
        return 1.0
    if not text_a or not text_b:
        return 0.0
    return difflib.SequenceMatcher(None, text_a, text_b, autojunk=False).ratio()


def compare_pair(
    identifier: str,
    old_path: Optional[Path],
    new_path: Optional[Path],
) -> dict:
    """
    Compare one PDF pair and return a result dictionary with keys:
        identifier, old_file, new_file, old_pages, new_pages,
        similarity, status, notes
    """
    result = {
        "identifier":  identifier,
        "old_file":    old_path.name if old_path else "-",
        "new_file":    new_path.name if new_path else "-",
        "old_pages":   "-",
        "new_pages":   "-",
        "similarity":  "-",
        "status":      "",
        "notes":       "",
    }

    # ── missing file edge cases ───────────────────────────────────────────────
    if old_path is None and new_path is None:
        result["status"] = STATUS_MISSING_BOTH
        return result

    if old_path is None:
        result["status"] = STATUS_MISSING_OLD
        result["new_pages"] = get_page_count(new_path)
        return result

    if new_path is None:
        result["status"] = STATUS_MISSING_NEW
        result["old_pages"] = get_page_count(old_path)
        return result

    # ── extract text ─────────────────────────────────────────────────────────
    old_text = extract_text(old_path)
    new_text = extract_text(new_path)

    if old_text is None or new_text is None:
        result["status"] = STATUS_UNREADABLE
        unreadable_files = []
        if old_text is None:
            unreadable_files.append(result["old_file"])
        if new_text is None:
            unreadable_files.append(result["new_file"])
        result["notes"] = f"Unreadable: {', '.join(unreadable_files)}"
        return result

    # ── page counts ───────────────────────────────────────────────────────────
    old_pages = get_page_count(old_path)
    new_pages = get_page_count(new_path)
    result["old_pages"] = old_pages
    result["new_pages"] = new_pages

    notes = []
    if old_pages != new_pages and old_pages != -1 and new_pages != -1:
        notes.append(f"Page count differs ({old_pages} vs {new_pages})")

    # ── normalise & compare ───────────────────────────────────────────────────
    norm_old = normalize(old_text)
    norm_new = normalize(new_text)

    ratio = _similarity(norm_old, norm_new)
    result["similarity"] = round(ratio, 4)
    result["status"] = STATUS_SAME if ratio >= SIMILARITY_THRESHOLD else STATUS_CHANGED

    if notes:
        result["notes"] = "; ".join(notes)

    return result
