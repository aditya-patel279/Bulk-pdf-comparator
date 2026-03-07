"""
utils/text_normalizer.py
Normalize extracted PDF text for fair comparison.
"""

import re


# Regex patterns for common timestamp / date formats to strip out
_TIMESTAMP_PATTERNS = [
    # HH:MM:SS or HH:MM
    re.compile(r"\b\d{1,2}:\d{2}(:\d{2})?\b"),
    # ISO date  YYYY-MM-DD
    re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
    # dd/mm/yyyy or mm/dd/yyyy
    re.compile(r"\b\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}\b"),
    # Month dd, yyyy  e.g. "March 7, 2026"
    re.compile(
        r"\b(?:january|february|march|april|may|june|july|august|september|"
        r"october|november|december)\s+\d{1,2},?\s+\d{4}\b",
        re.IGNORECASE,
    ),
    # Unix timestamps (10-digit numbers)
    re.compile(r"\b\d{10}\b"),
]


def normalize(text: str) -> str:
    """
    Normalise PDF text for comparison:
      - lowercase
      - remove timestamps / dates
      - collapse whitespace
    """
    if not text:
        return ""

    text = text.lower()

    for pattern in _TIMESTAMP_PATTERNS:
        text = pattern.sub(" ", text)

    # Collapse all whitespace (spaces, tabs, newlines) to a single space
    text = re.sub(r"\s+", " ", text).strip()

    return text
