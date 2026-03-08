"""
engine/comparator.py
Multi-stage PDF comparison pipeline.

Optimized with:
  - Stage 1: File hash check (instant identical file detection)
  - Stage 2: Page-level fingerprint comparison with early exit
  - rapidfuzz for 10-50x faster similarity computation
  - Parallel processing via ProcessPoolExecutor
  - Token-based comparison for layout independence
  - Performance logging
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from rapidfuzz import fuzz
    USE_RAPIDFUZZ = True
except ImportError:
    import difflib
    USE_RAPIDFUZZ = False

from engine.pdf_reader import (
    extract_text,
    get_page_count,
    compute_file_hash,
    get_pdf_metadata,
    iter_pages_with_fingerprints,
    PDFMetadata,
)
from utils.text_normalizer import normalize, normalize_tokens, compare_tokens

logger = logging.getLogger(__name__)

# ── configuration ─────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.99
MAX_WORKERS = min(8, (os.cpu_count() or 4))  # Limit parallel workers
ENABLE_PERFORMANCE_LOGGING = True  # Log timing for each comparison stage

# ── status constants ─────────────────────────────────────────────────────────
STATUS_SAME             = "SAME"
STATUS_CHANGED          = "CHANGED"
STATUS_MISSING_NEW      = "MISSING_NEW_FILE"
STATUS_MISSING_OLD      = "MISSING_OLD_FILE"
STATUS_UNREADABLE       = "UNREADABLE"
STATUS_MISSING_BOTH     = "MISSING_BOTH"
STATUS_ENCRYPTED        = "ENCRYPTED"
STATUS_CORRUPTED        = "CORRUPTED"

# ── in-memory caches ─────────────────────────────────────────────────────────
_text_cache: Dict[str, Optional[str]] = {}
_page_count_cache: Dict[str, int] = {}
_metadata_cache: Dict[str, PDFMetadata] = {}


@dataclass
class ComparisonTiming:
    """Timing information for performance logging."""
    hash_check_ms: float = 0.0
    page_fingerprint_ms: float = 0.0
    total_ms: float = 0.0
    early_exit_page: Optional[int] = None


def _file_cache_key(path: Path) -> str:
    """Quick hash based on file path + size + mtime for cache key."""
    stat = path.stat()
    return hashlib.md5(
        f"{path}|{stat.st_size}|{stat.st_mtime}".encode()
    ).hexdigest()


def _similarity(text_a: str, text_b: str) -> float:
    """
    Fast similarity ratio using rapidfuzz (if available) or difflib fallback.
    rapidfuzz is typically 10-50x faster than difflib.SequenceMatcher.
    """
    if not text_a and not text_b:
        return 1.0
    if not text_a or not text_b:
        return 0.0
    
    if USE_RAPIDFUZZ:
        # rapidfuzz returns 0-100, convert to 0-1
        return fuzz.ratio(text_a, text_b) / 100.0
    else:
        return difflib.SequenceMatcher(None, text_a, text_b, autojunk=False).ratio()


def _token_similarity(text_a: str, text_b: str) -> float:
    """
    Token-based similarity comparison.
    Handles layout differences by comparing sorted tokens.
    """
    tokens_a = normalize_tokens(text_a)
    tokens_b = normalize_tokens(text_b)
    return compare_tokens(tokens_a, tokens_b)


def _cached_metadata(path: Path) -> PDFMetadata:
    """Get PDF metadata with caching."""
    global _metadata_cache
    try:
        key = _file_cache_key(path)
        if key in _metadata_cache:
            return _metadata_cache[key]
        metadata = get_pdf_metadata(path)
        _metadata_cache[key] = metadata
        return metadata
    except Exception:
        return get_pdf_metadata(path)


def _cached_extract_text(path: Path) -> Optional[str]:
    """Extract text with caching to avoid repeated extraction."""
    global _text_cache
    try:
        key = _file_cache_key(path)
        if key in _text_cache:
            return _text_cache[key]
        text = extract_text(path)
        _text_cache[key] = text
        return text
    except Exception:
        return extract_text(path)


def _cached_page_count(path: Path) -> int:
    """Get page count with caching."""
    global _page_count_cache
    try:
        key = _file_cache_key(path)
        if key in _page_count_cache:
            return _page_count_cache[key]
        count = get_page_count(path)
        _page_count_cache[key] = count
        return count
    except Exception:
        return get_page_count(path)


def clear_cache():
    """Clear all caches."""
    global _text_cache, _page_count_cache, _metadata_cache
    _text_cache.clear()
    _page_count_cache.clear()
    _metadata_cache.clear()


def compare_pair(
    identifier: str,
    old_path: Optional[Path],
    new_path: Optional[Path],
    use_page_fingerprints: bool = True,
) -> dict:
    """
    Multi-stage PDF comparison pipeline.
    
    Stage 1: File hash check — instant identical file detection
    Stage 2: Page-level fingerprint comparison with early exit
    Stage 3: Full text comparison (fallback)
    
    Returns:
        Result dictionary with keys: identifier, old_file, new_file, 
        old_pages, new_pages, similarity, status, notes
    """
    start_time = time.time()
    timing = ComparisonTiming()
    
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

    # ── Handle missing files ───────────────────────────────────────────────
    if old_path is None and new_path is None:
        result["status"] = STATUS_MISSING_BOTH
        return result

    if old_path is None:
        result["status"] = STATUS_MISSING_OLD
        result["new_pages"] = _cached_page_count(new_path)
        return result

    if new_path is None:
        result["status"] = STATUS_MISSING_NEW
        result["old_pages"] = _cached_page_count(old_path)
        return result

    # ── Get PDF metadata (includes file hash, encryption check, etc.) ─────────
    old_meta = _cached_metadata(old_path)
    new_meta = _cached_metadata(new_path)
    
    result["old_pages"] = old_meta.page_count
    result["new_pages"] = new_meta.page_count
    notes = []
    
    # Handle corrupted PDFs
    if old_meta.is_corrupted or new_meta.is_corrupted:
        result["status"] = STATUS_CORRUPTED
        corrupted = []
        if old_meta.is_corrupted:
            corrupted.append(result["old_file"])
        if new_meta.is_corrupted:
            corrupted.append(result["new_file"])
        result["notes"] = f"Corrupted: {', '.join(corrupted)}"
        return result
    
    # Handle encrypted PDFs
    if old_meta.is_encrypted or new_meta.is_encrypted:
        result["status"] = STATUS_ENCRYPTED
        encrypted = []
        if old_meta.is_encrypted:
            encrypted.append(result["old_file"])
        if new_meta.is_encrypted:
            encrypted.append(result["new_file"])
        result["notes"] = f"Encrypted: {', '.join(encrypted)}"
        return result

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 1: File Hash Check
    # If MD5 hashes match, files are identical — skip all further processing
    # ═══════════════════════════════════════════════════════════════════════════
    hash_start = time.time()
    
    if old_meta.file_hash and new_meta.file_hash:
        if old_meta.file_hash == new_meta.file_hash:
            timing.hash_check_ms = (time.time() - hash_start) * 1000
            timing.total_ms = (time.time() - start_time) * 1000
            
            result["similarity"] = 1.0
            result["status"] = STATUS_SAME
            result["notes"] = "Identical files (hash match)"
            
            if ENABLE_PERFORMANCE_LOGGING:
                logger.info(
                    "PDF %s compared in %.1f ms (hash match, skipped content check)",
                    identifier, timing.total_ms
                )
            return result
    
    timing.hash_check_ms = (time.time() - hash_start) * 1000
    
    # Check page count difference
    if old_meta.page_count != new_meta.page_count:
        if old_meta.page_count != -1 and new_meta.page_count != -1:
            notes.append(f"Page count differs ({old_meta.page_count} vs {new_meta.page_count})")

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 2: Page-level Fingerprint Comparison (with early exit)
    # Compare pages one-by-one and stop as soon as a difference is found
    # ═══════════════════════════════════════════════════════════════════════════
    if use_page_fingerprints and old_meta.page_count > 0 and new_meta.page_count > 0:
        fingerprint_start = time.time()
        
        # Different page counts = definitely changed
        if old_meta.page_count != new_meta.page_count:
            timing.page_fingerprint_ms = (time.time() - fingerprint_start) * 1000
            timing.total_ms = (time.time() - start_time) * 1000
            
            result["similarity"] = 0.0  # Will be computed more accurately below
            result["status"] = STATUS_CHANGED
            notes.append("Early exit: page count mismatch")
            result["notes"] = "; ".join(notes)
            
            # Still need to compute actual similarity for reporting
            # Fall through to full comparison
        else:
            # Same page count — compare page fingerprints
            try:
                old_pages_iter = iter_pages_with_fingerprints(old_path, use_ocr=True)
                new_pages_iter = iter_pages_with_fingerprints(new_path, use_ocr=True)
                
                all_match = True
                changed_page = None
                
                for old_page, new_page in zip(old_pages_iter, new_pages_iter):
                    if old_page.fingerprint != new_page.fingerprint:
                        all_match = False
                        changed_page = old_page.index + 1  # 1-indexed for user
                        timing.early_exit_page = changed_page
                        break
                
                timing.page_fingerprint_ms = (time.time() - fingerprint_start) * 1000
                
                if all_match:
                    # All pages match!
                    timing.total_ms = (time.time() - start_time) * 1000
                    
                    result["similarity"] = 1.0
                    result["status"] = STATUS_SAME
                    result["notes"] = "All page fingerprints match"
                    
                    if ENABLE_PERFORMANCE_LOGGING:
                        logger.info(
                            "PDF %s compared in %.1f ms (hash: %.1f ms, fingerprints: %.1f ms) - SAME",
                            identifier, timing.total_ms, timing.hash_check_ms, timing.page_fingerprint_ms
                        )
                    return result
                else:
                    # Found difference — early exit
                    timing.total_ms = (time.time() - start_time) * 1000
                    
                    result["similarity"] = 0.0  # Approximate, actual computed below if needed
                    result["status"] = STATUS_CHANGED
                    notes.append(f"Difference found at page {changed_page}")
                    result["notes"] = "; ".join(notes)
                    
                    if ENABLE_PERFORMANCE_LOGGING:
                        logger.info(
                            "PDF %s compared in %.1f ms (early exit at page %d) - CHANGED",
                            identifier, timing.total_ms, changed_page
                        )
                    return result
                    
            except Exception as exc:
                logger.debug("Page fingerprint comparison failed, falling back to full text: %s", exc)
                # Fall through to full text comparison

    # ═══════════════════════════════════════════════════════════════════════════
    # STAGE 3: Full Text Comparison (fallback)
    # Extract full text and compute similarity ratio
    # ═══════════════════════════════════════════════════════════════════════════
    old_text = _cached_extract_text(old_path)
    new_text = _cached_extract_text(new_path)

    if old_text is None or new_text is None:
        result["status"] = STATUS_UNREADABLE
        unreadable_files = []
        if old_text is None:
            unreadable_files.append(result["old_file"])
        if new_text is None:
            unreadable_files.append(result["new_file"])
        result["notes"] = f"Unreadable: {', '.join(unreadable_files)}"
        return result

    # Normalize and compare using token-based similarity (handles layout differences)
    norm_old = normalize(old_text)
    norm_new = normalize(new_text)
    
    # Use token-based comparison for layout independence
    token_ratio = _token_similarity(old_text, new_text)
    
    # Also compute traditional similarity for reference
    text_ratio = _similarity(norm_old, norm_new)
    
    # Use the higher of the two (token comparison handles table layouts better)
    ratio = max(token_ratio, text_ratio)
    
    result["similarity"] = round(ratio, 4)
    result["status"] = STATUS_SAME if ratio >= SIMILARITY_THRESHOLD else STATUS_CHANGED

    if notes:
        result["notes"] = "; ".join(notes)

    timing.total_ms = (time.time() - start_time) * 1000
    
    if ENABLE_PERFORMANCE_LOGGING:
        logger.info(
            "PDF %s compared in %.1f ms (full text comparison) - %s",
            identifier, timing.total_ms, result["status"]
        )

    return result


# ── Worker function for multiprocessing ───────────────────────────────────────
def _compare_pair_worker(args: Tuple) -> dict:
    """
    Worker function for ProcessPoolExecutor.
    Takes a tuple (identifier, old_path_str, new_path_str) to avoid Path pickling issues.
    """
    identifier, old_path_str, new_path_str = args
    old_path = Path(old_path_str) if old_path_str else None
    new_path = Path(new_path_str) if new_path_str else None
    
    try:
        return compare_pair(identifier, old_path, new_path)
    except Exception as exc:
        return {
            "identifier": identifier,
            "old_file":   old_path.name if old_path else "-",
            "new_file":   new_path.name if new_path else "-",
            "old_pages":  "-",
            "new_pages":  "-",
            "similarity": "-",
            "status":     STATUS_UNREADABLE,
            "notes":      str(exc),
        }


def compare_pairs_parallel(
    pairs: List[Dict],
    max_workers: Optional[int] = None,
    progress_callback=None,
) -> List[dict]:
    """
    Compare multiple PDF pairs in parallel using ProcessPoolExecutor.
    
    Args:
        pairs: List of dicts with keys: identifier, old_file (Path|None), new_file (Path|None)
        max_workers: Number of parallel workers (default: auto based on CPU count)
        progress_callback: Optional callable(completed_count, total_count) for progress updates
    
    Returns:
        List of result dicts in the same order as input pairs
    """
    if max_workers is None:
        max_workers = MAX_WORKERS
    
    total = len(pairs)
    if total == 0:
        return []
    
    # Convert to serializable format (Path objects can't be pickled across processes)
    work_items = [
        (
            p["identifier"],
            str(p["old_file"]) if p["old_file"] else None,
            str(p["new_file"]) if p["new_file"] else None,
        )
        for p in pairs
    ]
    
    # For small batches, run sequentially to avoid process overhead
    if total <= 3:
        results = []
        for i, args in enumerate(work_items):
            results.append(_compare_pair_worker(args))
            if progress_callback:
                progress_callback(i + 1, total)
        return results
    
    # Parallel execution
    results = [None] * total
    completed = 0
    
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks with their index for result ordering
        future_to_idx = {
            executor.submit(_compare_pair_worker, args): idx
            for idx, args in enumerate(work_items)
        }
        
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                # Fallback result on worker error
                results[idx] = {
                    "identifier": pairs[idx]["identifier"],
                    "old_file":   pairs[idx]["old_file"].name if pairs[idx]["old_file"] else "-",
                    "new_file":   pairs[idx]["new_file"].name if pairs[idx]["new_file"] else "-",
                    "old_pages":  "-",
                    "new_pages":  "-",
                    "similarity": "-",
                    "status":     STATUS_UNREADABLE,
                    "notes":      f"Worker error: {exc}",
                }
            
            completed += 1
            if progress_callback:
                progress_callback(completed, total)
    
    return results
