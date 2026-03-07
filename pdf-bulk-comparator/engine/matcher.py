"""
engine/matcher.py
Build old/new PDF file pairs matched by numeric identifier prefix.

Identifier = filename.split("_")[0]
e.g.  "001_invoice_old.pdf"  →  identifier "001"
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


def build_file_map(folder_path: str | Path) -> Dict[str, Path]:
    """
    Scan *folder_path* for PDF files and return a mapping:
        { identifier: Path }

    Duplicate identifiers are logged as warnings; the first file
    encountered (alphabetical order) is kept.
    """
    folder = Path(folder_path)
    file_map: Dict[str, Path] = {}
    duplicates: List[str] = []

    pdf_files = sorted(folder.glob("*.pdf"))
    for pdf_file in pdf_files:
        parts = pdf_file.stem.split("_")
        identifier = parts[0]

        if identifier in file_map:
            duplicates.append(identifier)
            logger.warning(
                "Duplicate identifier '%s': '%s' already mapped to '%s'. "
                "Skipping '%s'.",
                identifier,
                identifier,
                file_map[identifier].name,
                pdf_file.name,
            )
        else:
            file_map[identifier] = pdf_file

    return file_map, duplicates


def build_pairs(
    old_map: Dict[str, Path],
    new_map: Dict[str, Path],
) -> List[Dict]:
    """
    Combine old and new file maps into a list of comparison pairs.

    Each element is a dict:
        {
            "identifier": str,
            "old_file":   Path | None,
            "new_file":   Path | None,
        }
    """
    all_identifiers = sorted(set(old_map.keys()) | set(new_map.keys()))

    pairs: List[Dict] = []
    for ident in all_identifiers:
        pairs.append(
            {
                "identifier": ident,
                "old_file": old_map.get(ident),
                "new_file": new_map.get(ident),
            }
        )

    return pairs
