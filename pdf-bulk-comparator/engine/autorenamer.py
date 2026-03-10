"""
engine/autorenamer.py
Matches OLD and NEW PDFs by filename similarity (pass 1) then content
similarity (pass 2), and renames them as 001_..., 002_..., 003_... pairs
so the comparison tool can work correctly.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Optional

try:
    from rapidfuzz import fuzz as _rfuzz
    _USE_RAPIDFUZZ = True
except ImportError:
    from difflib import SequenceMatcher as _SM
    _USE_RAPIDFUZZ = False

NAME_THRESHOLD    = 0.60
CONTENT_THRESHOLD = 0.45


def _similarity(a: str, b: str) -> float:
    if _USE_RAPIDFUZZ:
        return _rfuzz.ratio(a, b) / 100.0
    return _SM(None, a, b).ratio()


@lru_cache(maxsize=1024)
def clean_name(filename: str) -> str:
    name = Path(filename).stem
    name = re.sub(r"^\d{1,4}_+", "", name)
    name = re.sub(r"[_\-\s]+", " ", name).strip().lower()
    return name


def name_similarity(a: str, b: str) -> float:
    return _similarity(clean_name(a), clean_name(b))


def _extract_text_snippet(path: Path, max_chars: int = 800) -> str:
    try:
        import pdfplumber  # noqa: PLC0415
        with pdfplumber.open(path) as pdf:
            text = ""
            for page in pdf.pages[:3]:
                text += page.extract_text() or ""
                if len(text) >= max_chars:
                    break
        return text[:max_chars].lower()
    except Exception:
        return ""


def _preload_snippets(
    paths: List[Path],
    progress_cb: Optional[Callable[[int], None]] = None,
    progress_base: int = 50,
    progress_span: int = 10,
) -> Dict[Path, str]:
    """Extract text snippets from all paths in parallel (I/O-bound)."""
    cache: Dict[Path, str] = {}
    total = max(len(paths), 1)
    done  = 0

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_extract_text_snippet, p): p for p in paths}
        for fut in futures:
            path = futures[fut]
            try:
                cache[path] = fut.result()
            except Exception:
                cache[path] = ""
            done += 1
            if progress_cb:
                progress_cb(min(progress_base + int(done / total * progress_span), 99))

    return cache


def build_matches(
    old_files: List[Path],
    new_files: List[Path],
    progress_cb: Optional[Callable[[int], None]] = None,
) -> List[dict]:
    """
    Content-based matching:
      Step 1 — parallel text extraction              → progress 0–30%
      Step 2 — content similarity scoring            → progress 30–100%
    """
    pairs: List[dict] = []
    used_new: set[Path] = set()

    all_paths = list(set(old_files) | set(new_files))
    snippet_cache = _preload_snippets(
        all_paths,
        progress_cb=progress_cb,
        progress_base=0,
        progress_span=30,
    )

    if progress_cb:
        progress_cb(30)

    remaining = list(new_files)
    total_content_ops = max(len(old_files) * len(new_files), 1)
    content_done = 0

    for o in old_files:
        best_score: float = 0.0
        best_n: Optional[Path] = None
        ta = snippet_cache.get(o, "")

        if not ta:
            pairs.append({"old": o, "new": None, "method": "unmatched_old", "score": 0.0})
            content_done += len(remaining)
            continue

        for n in remaining:
            if n in used_new:
                content_done += 1
                continue
            tb = snippet_cache.get(n, "")
            if not tb:
                content_done += 1
                continue
            s = _similarity(ta, tb)
            if s > best_score:
                best_score, best_n = s, n
            content_done += 1
            if progress_cb and content_done % 20 == 0:
                progress_cb(min(30 + int(content_done / total_content_ops * 70), 99))

        if best_score >= CONTENT_THRESHOLD and best_n:
            pairs.append({"old": o, "new": best_n, "method": "content", "score": best_score})
            used_new.add(best_n)
        else:
            pairs.append({"old": o, "new": None, "method": "unmatched_old", "score": best_score})

    # ── Leftover NEW files with no OLD match ─────────────────────────────────
    for n in new_files:
        if n not in used_new:
            pairs.append({"old": None, "new": n, "method": "unmatched_new", "score": 0.0})

    # ── Assign sequential IDs (sorted by cleaned old name) ───────────────────
    matched   = [p for p in pairs if p["old"] and p["new"]]
    unmatched = [p for p in pairs if not (p["old"] and p["new"])]

    matched.sort(key=lambda p: clean_name(p["old"].name))  # type: ignore[arg-type]
    for i, p in enumerate(matched, start=1):
        p["id"] = i
    for p in unmatched:
        p["id"] = None

    if progress_cb:
        progress_cb(100)

    return matched + unmatched


def do_rename(pairs: List[dict]) -> List[tuple]:
    """
    Rename files in-place using their stored Path objects.
    Strips any existing numeric prefix before adding the new one.
    Returns list of (status, src, dst, error_msg).
    """
    log: List[tuple] = []
    for p in pairs:
        if p["id"] is None:
            continue
        prefix = f"{p['id']:03d}_"

        for filepath in (p["old"], p["new"]):
            if filepath is None:
                continue
            src: Path = Path(filepath)
            new_name  = prefix + re.sub(r"^\d{1,4}_+", "", src.name)
            dst       = src.parent / new_name

            if src == dst:
                log.append(("skip", str(src), str(dst), ""))
                continue
            if dst.exists():
                log.append(("error", str(src), str(dst), "Destination already exists"))
                continue
            try:
                src.rename(dst)
                log.append(("ok", str(src), str(dst), ""))
            except Exception as exc:
                log.append(("error", str(src), str(dst), str(exc)))
    return log
